#include "device_runtime.h"

#include "entry/EasyUIContext.h"

extern "C" {

void onEasyUIInit(EasyUIContext*) {
    dashboard::flythings::DeviceRuntime::instance().start();
}

void onEasyUIDeinit(EasyUIContext*) {
    dashboard::flythings::DeviceRuntime::instance().stop();
}

const char* onStartupApp(EasyUIContext*) {
    return "mainActivity";
}

}  // extern "C"
