#pragma once

#include "app/Activity.h"
#include "control/ZKTextView.h"

class mainActivity : public Activity {
public:
    mainActivity() = default;
    ~mainActivity() override = default;

protected:
    const char* getAppName() const override;
    void onCreate() override;
    void onResume() override;
    bool onTimer(int id) override;

private:
    void updateDashboard();

    ZKTextView* speed_{nullptr};
    ZKTextView* range_{nullptr};
    ZKTextView* soc_{nullptr};
    ZKTextView* doors_{nullptr};
    ZKTextView* tire_front_{nullptr};
    ZKTextView* tire_rear_{nullptr};
    ZKTextView* clock_{nullptr};
    ZKBase* gear_{nullptr};
};
