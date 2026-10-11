import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins

PluginSettings {
    id: root
    pluginId: "screenTime"

    // Set by DMS when this page is shown for a single desktop widget instance;
    // values saved then go to that instance only, so only widget options are shown.
    property string instanceId: ""
    property var instanceData: null
    readonly property bool isInstance: instanceId !== ""

    readonly property var today: PluginService.globalVars["screenTime"]?.cache?.["day:"]?.data ?? null
    readonly property var cli: PluginService.globalVars["screenTime"]?.cli ?? null

    StyledText {
        visible: !root.isInstance
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
        visible: !root.isInstance
        width: parent.width
        text: I18n.trFor("screenTime", "Tracking")
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.DemiBold
        color: Theme.surfaceText
    }

    SelectionSetting {
        visible: !root.isInstance
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
        visible: !root.isInstance
        settingKey: "trackTitles"
        label: I18n.trFor("screenTime", "Record window titles")
        description: I18n.trFor("screenTime", "Store window titles alongside apps. Off by default for privacy; applies to new data only.")
        defaultValue: false
    }

    SelectionSetting {
        visible: !root.isInstance
        settingKey: "titleRetention"
        label: I18n.trFor("screenTime", "Keep window titles for")
        description: I18n.trFor("screenTime", "Older titles are deleted; the time spent per app is kept.")
        options: [
            { label: I18n.trFor("screenTime", "7 days"), value: "7" },
            { label: I18n.trFor("screenTime", "30 days"), value: "30" },
            { label: I18n.trFor("screenTime", "90 days"), value: "90" },
            { label: I18n.trFor("screenTime", "1 year"), value: "365" },
            { label: I18n.trFor("screenTime", "Forever"), value: "0" }
        ]
        defaultValue: "30"
    }

    SelectionSetting {
        visible: !root.isInstance
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
        visible: !root.isInstance
        width: parent.width
        text: I18n.trFor("screenTime", "Display")
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.DemiBold
        color: Theme.surfaceText
    }

    SelectionSetting {
        visible: !root.isInstance
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
        visible: !root.isInstance
        settingKey: "showTopAppIcon"
        label: I18n.trFor("screenTime", "Show top app icon")
        description: I18n.trFor("screenTime", "Show the most used app's icon in the bar instead of the hourglass.")
        defaultValue: true
    }


    StyledText {
        visible: !root.isInstance
        width: parent.width
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        text: I18n.trFor("screenTime", "Categories are edited in ~/.config/screentime/categories.toml.")
    }

    // -- desktop widget instance -------------------------------------------------

    StyledText {
        visible: root.isInstance
        width: parent.width
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        text: I18n.trFor("screenTime", "Tracking options (idle timeout, window titles, …) are in Settings → Plugins → Screen Time.")
    }

    SelectionSetting {
        visible: root.isInstance
        settingKey: "view"
        label: I18n.trFor("screenTime", "Shows")
        description: I18n.trFor("screenTime", "Today with an hourly chart, or this week with a daily chart.")
        options: [
            { label: I18n.trFor("screenTime", "Today"), value: "day" },
            { label: I18n.trFor("screenTime", "This week"), value: "week" }
        ]
        defaultValue: "day"
    }

    ToggleSetting {
        visible: root.isInstance
        settingKey: "openOnClick"
        label: I18n.trFor("screenTime", "Open details on click")
        description: I18n.trFor("screenTime", "Left click opens the Screen Time popout from the bar on the same screen.")
        defaultValue: true
    }

    SliderSetting {
        visible: root.isInstance
        settingKey: "desktopOpacity"
        label: I18n.trFor("screenTime", "Background opacity")
        defaultValue: 85
        minimum: 0
        maximum: 100
        unit: "%"
    }
}
