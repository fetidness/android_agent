plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "net.sys32.agent"
    compileSdk = 36
    ndkVersion = "29.0.14206865"   // NDK 27 da SIGSEGV pe acest host (vezi memorie)

    defaultConfig {
        applicationId = "net.sys32.agent"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        ndk { abiFilters += listOf("arm64-v8a") }  // P2: doar arm64 (device real); x86_64 = -20.6MB
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    androidResources {
        // modelele whisper (.bin) NU se comprima: altfel prima extragere e lenta
        noCompress += listOf("bin", "gguf")
    }
    packaging {
        jniLibs { useLegacyPackaging = true }
        // .so livrat precompilat + wrapper-ul JNI compilat din surse
        // ★ imaginea rootfs-ului Debian (assets/proot/agentroot.tar.gz, ~230 MB) ajunge in APK
        // ca lib/arm64-v8a/libagentroot_exec.so: DECOMPRIMATA si cu insigne de biblioteca. Doar
        // asa o poate citi adbd (uid 2000 NU are voie in app_data_file, SELinux) si doar asa
        // instalarea Debianului merge FARA nicio descarcare de pe telefon.
        jniLibs { keepDebugSymbols += "**/libagentroot_exec.so" }
    }
}

// Modelul vocal (63 MB) NU e in git: se descarca automat inainte de build daca lipseste,
// ca o clona noua sa functioneze out of the box (vezi fetch_model.sh din radacina proiectului).
val fetchModel = tasks.register<Exec>("fetchModel") {
    workingDir = rootProject.projectDir
    commandLine("bash", "fetch_model.sh")
}

// Modelul Whisper de recunoastere (1.5 GB) NU e in git: se descarca automat inainte de
// build daca lipseste, exact ca modelul vocal (ca o clona noua sa functioneze out of the box).
val fetchWhisper = tasks.register<Exec>("fetchWhisper") {
    workingDir = rootProject.projectDir
    commandLine("bash", "fetch_whisper.sh")
}

// Rootfs-ul Debian (python3 + gcc, fara apt la runtime) se construieste daca lipseste:
// tools/build_rootfs.sh (debootstrap, o singura data pe host) -> assets/proot/agentroot.tar.gz.
// La build devine jniLibs/arm64-v8a/libagentroot_exec.so prin task-ul stageRootfs (mai jos).
val fetchRootfs = tasks.register<Exec>("fetchRootfs") {
    workingDir = rootProject.projectDir
    commandLine("bash", "fetch_rootfs.sh")
}

// ★ Rootfs-ul Debian: arhiva din assets NU ajunge automat in APK ca libagentroot_exec.so.
// Conversia se face aici (inainte de mergeJniLibFolders), altfel APK-ul iese FARA rootfs si
// instalarea automata a Debianului pe telefoane fara root nu mai exista (regresie 6 nov 2026).
// Task-ul e idempotent: sare peste copiere daca sursa si tinta au aceeasi marime si mtime.
val rootfsSrc = layout.projectDirectory.file("src/main/assets/proot/agentroot.tar.gz")
val rootfsDst = layout.projectDirectory.file("src/main/jniLibs/arm64-v8a/libagentroot_exec.so")
val stageRootfs = tasks.register("stageRootfs") {
    val src = rootfsSrc.asFile
    val dst = rootfsDst.asFile
    inputs.file(src)
    outputs.file(dst)
    doLast {
        if (!src.exists()) {
            logger.lifecycle("[rootfs] LIPSESTE ${src} - se sare peste (ruleaza fetch_rootfs.sh)")
            return@doLast
        }
        if (dst.exists() && dst.length() == src.length() && dst.lastModified() >= src.lastModified()) {
            logger.lifecycle("[rootfs] deja la loc: ${dst.name} ${dst.length()} B")
            return@doLast
        }
        dst.parentFile.mkdirs()
        src.copyTo(dst, overwrite = true)
        dst.setLastModified(src.lastModified())
        logger.lifecycle("[rootfs] copiat ${src.name} -> jniLibs/${dst.name} ${dst.length()} B")
    }
}

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("JniLibFolders") }
    .configureEach { dependsOn(stageRootfs) }

tasks.named("preBuild") { dependsOn(fetchModel, fetchWhisper, fetchRootfs, stageRootfs) }

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    // DexMaker: genereaza clase la runtime (subclasare de clase abstracte)
    implementation("com.linkedin.dexmaker:dexmaker:2.28.3")
}
