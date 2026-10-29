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
    packaging {
        jniLibs { useLegacyPackaging = true }
        // .so livrat precompilat + wrapper-ul JNI compilat din surse
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    // DexMaker: genereaza clase la runtime (subclasare de clase abstracte)
    implementation("com.linkedin.dexmaker:dexmaker:2.28.3")
}
