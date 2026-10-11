import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins

PluginSettings {
    id: root
    pluginId: "screenTime"

    readonly property var today: PluginService.globalVars["screenTime"]?.cache?.["day:"]?.data ?? null
    readonly property var cli: PluginService.globalVars["screenTime"]?.cli ?? null

    StyledText {
        width: parent.width
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: root.today && root.today.daemon.running ? Theme.surfaceVariantText : Theme.error
        text: {
            if (root.cli && root.cli.missing)
                return I18n.trFor("screenTime", "The screentime CLI was not found. Run install.sh from the screen-time repository.");
            if (!root.today)
                return I18n.trFor("screenTime", "Checking the tracker…");
            if (!root.today.daemon.running)
                return I18n.trFor("screenTime", "The tracker is not running: systemctl --user enable --now screentime");
            return root.today.daemon.idle_detection
                ? I18n.trFor("screenTime", "Tracker running, idle detection on.")
                : I18n.trFor("screenTime", "Tracker running, but idle detection is off (install swayidle or set an idle timeout).");
        }
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("screenTime", "Tracking")
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.DemiBold
        color: Theme.surfaceText
    }

    SelectionSetting {
        settingKey: "idleTimeout"
        label: I18n.trFor("screenTime", "Idle timeout")
        description: I18n.trFor("screenTime", "Stop counting after this long without input. Video players that keep the screen awake still count.")
        options: [
            { label: I18n.trFor("screenTime", "Off"), value: "0" },
            { label: "1 min", value: "60" },
            { label: "2 min", value: "120" },
            { label: "3 min", value: "180" },
            { label: "5 min", value: "300" },
            { label: "10 min", value: "600" },
            { label: "15 min", value: "900" },
            { label: "30 min", value: "1800" }
        ]
        defaultValue: "300"
    }

    ToggleSetting {
        settingKey: "trackTitles"
        label: I18n.trFor("screenTime", "Record window titles")
        description: I18n.trFor("screenTime", "Store window titles alongside apps. Off by default for privacy; applies to new data only.")
        defaultValue: false
    }

    SelectionSetting {
        settingKey: "dayStartHour"
        label: I18n.trFor("screenTime", "Day starts at")
        description: I18n.trFor("screenTime", "Late-night usage before this hour counts towards the previous day.")
        options: [
            { label: I18n.trFor("screenTime", "Midnight"), value: "0" },
            { label: "01:00", value: "1" },
            { label: "02:00", value: "2" },
            { label: "03:00", value: "3" },
            { label: "04:00", value: "4" },
            { label: "05:00", value: "5" },
            { label: "06:00", value: "6" }
        ]
        defaultValue: "0"
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("screenTime", "Display")
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.DemiBold
        color: Theme.surfaceText
    }

    SelectionSetting {
        settingKey: "refreshInterval"
        label: I18n.trFor("screenTime", "Refresh interval")
        description: I18n.trFor("screenTime", "How often the bar updates. The popout always refreshes when opened.")
        options: [
            { label: "30 s", value: "30" },
            { label: "1 min", value: "60" },
            { label: "2 min", value: "120" },
            { label: "5 min", value: "300" }
        ]
        defaultValue: "60"
    }

    ToggleSetting {
        settingKey: "showTopAppIcon"
        label: I18n.trFor("screenTime", "Show top app icon")
        description: I18n.trFor("screenTime", "Show the most used app's icon in the bar instead of the hourglass.")
        defaultValue: true
    }

    SliderSetting {
        settingKey: "desktopOpacity"
        label: I18n.trFor("screenTime", "Desktop widget background")
        description: I18n.trFor("screenTime", "Background opacity of the desktop widget.")
        defaultValue: 85
        minimum: 0
        maximum: 100
        unit: "%"
    }

    StyledText {
        width: parent.width
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        text: I18n.trFor("screenTime", "Categories are edited in ~/.config/screentime/categories.toml.")
    }
}
