package net.sys32.agent

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent

// FIX 8: receiver explicit de Device Admin. Cu device owner activat
// (dpm set-device-owner net.sys32.agent/.AgentDeviceAdmin) se deblocheaza
// wipeData, resetPassword, setCameraDisabled, setApplicationHidden, kiosk etc.
class AgentDeviceAdmin : DeviceAdminReceiver() {
    override fun onEnabled(context: Context, intent: Intent) {}
    override fun onDisabled(context: Context, intent: Intent) {}
    override fun onDisableRequested(context: Context, intent: Intent): CharSequence =
        "Agent ramane administrator de dispozitiv."
}
