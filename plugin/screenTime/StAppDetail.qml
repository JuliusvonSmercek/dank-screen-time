import QtQuick
import qs.Common
import qs.Widgets
import "StFormat.js" as Fmt

// One app's numbers: header, stat tiles and its daily usage chart
// (past 7 days in Day view, the selected week in Week view).
Column {
    id: root

    property var app: null
    property var summary: null
    property string kind: "day"
    property string rangeLabel: ""

    signal back

    function tr(s) {
        return I18n.trFor("screenTime", s);
    }

    readonly property var history: app ? app.history : []
    readonly property var dates: summary ? summary.history_dates : []
    readonly property real historyTotal: history.reduce((a, b) => a + b, 0)
    readonly property int elapsedDays: {
        if (!summary)
            return 1;
        let n = 0;
        for (let i = 0; i < dates.length; i++) {
            if (dates[i] <= summary.range.today)
                n++;
        }
        return Math.max(1, n);
    }

    spacing: Theme.spacingM

    // Header: back, icon, name, category.
    Item {
        width: parent.width
        height: 56

        DankActionButton {
            id: backButton
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            iconName: "arrow_back"
            buttonSize: 36
            onClicked: root.back()
        }

        StAppIcon {
            id: bigIcon
            anchors.left: backButton.right
            anchors.leftMargin: Theme.spacingS
            anchors.verticalCenter: parent.verticalCenter
            iconSize: 44
            appId: root.app ? root.app.app_id : ""
            icon: root.app ? (root.app.icon || "") : ""
            name: root.app ? root.app.name : ""
        }

        Column {
            anchors.left: bigIcon.right
            anchors.leftMargin: Theme.spacingM
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            StyledText {
                width: parent.width
                elide: Text.ElideRight
                text: root.app ? root.app.name : ""
                font.pixelSize: Theme.fontSizeLarge + 2
                font.weight: Font.DemiBold
                color: Theme.surfaceText
            }
            StyledText {
                width: parent.width
                elide: Text.ElideRight
                text: root.app ? (root.app.category || root.app.app_id) : ""
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }
        }
    }

    // Stat tiles.
    Row {
        id: tiles
        width: parent.width
        spacing: Theme.spacingS

        readonly property real tileWidth: (width - spacing * 2) / 3

        Repeater {
            model: [
                { label: root.rangeLabel, value: Fmt.duration(root.app ? root.app.seconds : 0) },
                {
                    label: root.kind === "day" ? root.tr("7-day average") : root.tr("Per day"),
                    value: Fmt.duration(root.kind === "day" ? root.historyTotal / 7 : (root.app ? root.app.seconds : 0) / root.elapsedDays)
                },
                { label: root.tr("Share"), value: Math.round((root.app ? root.app.share : 0) * 100) + " %" }
            ]

            Rectangle {
                required property var modelData
                width: tiles.tileWidth
                height: 68
                radius: Theme.cornerRadius
                color: Theme.nestedSurface
                border.color: Theme.outlineMedium
                border.width: 1

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spacingM
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.spacingS
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    StyledText {
                        width: parent.width
                        elide: Text.ElideRight
                        text: modelData.label
                        font.pixelSize: Theme.fontSizeSmall - 1
                        color: Theme.surfaceVariantText
                    }
                    NumericText {
                        width: parent.width
                        elide: Text.ElideRight
                        isMonospace: false
                        text: modelData.value
                        font.pixelSize: Theme.fontSizeLarge
                        font.weight: Font.DemiBold
                        color: Theme.surfaceText
                    }
                }
            }
        }
    }

    StCard {
        width: parent.width
        title: root.kind === "day" ? root.tr("Past 7 days") : root.tr("Daily usage")
        pad: Theme.spacingL

        StBarChart {
            id: chart
            width: parent.width
            height: 150
            unit: "day"
            averageSeconds: root.historyTotal > 0 ? root.historyTotal / (root.kind === "day" ? 7 : root.elapsedDays) : -1
            buckets: {
                if (!root.summary || !root.app)
                    return [];
                const loc = Qt.locale();
                const today = root.summary.range.today;
                const out = [];
                for (let i = 0; i < root.dates.length; i++) {
                    const d = Fmt.parseDate(root.dates[i]);
                    out.push({
                        seconds: root.history[i] || 0,
                        is_current: root.dates[i] === (root.kind === "day" ? root.summary.range.anchor : today),
                        is_future: root.dates[i] > today,
                        label: loc.dayName(d.getDay(), Locale.ShortFormat),
                        tip: d.toLocaleDateString(loc, "ddd, d MMM") + " · " + Fmt.duration(root.history[i] || 0)
                    });
                }
                return out;
            }
        }
    }

    // Replay the grow-in only when a different app is opened, not on refresh.
    readonly property string appKey: app ? app.app_id : ""
    onAppKeyChanged: {
        if (appKey)
            chart.replay();
    }
}
