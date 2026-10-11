import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "StFormat.js" as Fmt

PopoutComponent {
    id: root

    readonly property string pid: "screenTime"
    property real bodyHeight: 560

    // -- view state ------------------------------------------------------
    property string kind: PluginService.getGlobalVar(pid, "lastKind", "day")
    property string anchor: ""                 // "" = today / this week
    property string detailAppId: ""
    readonly property string key: kind + ":" + anchor

    readonly property var cacheMap: PluginService.globalVars[pid]?.cache ?? ({})
    readonly property var cli: PluginService.globalVars[pid]?.cli ?? null
    readonly property var entry: cacheMap[key] ?? null
    property var shown: null                   // last data that matched a key, kept while loading
    readonly property bool loading: entry === null
    readonly property var range: shown ? shown.range : null
    readonly property bool isCurrent: range ? range.is_current : true
    readonly property var detailApp: {
        if (!shown || !detailAppId)
            return null;
        const apps = shown.apps || [];
        for (let i = 0; i < apps.length; i++) {
            if (apps[i].app_id === detailAppId)
                return apps[i];
        }
        return null;
    }

    function tr(s) {
        return I18n.trFor("screenTime", s);
    }

    function request(force) {
        PluginService.setGlobalVar(pid, "request", { key: key, force: force, t: Date.now() });
    }

    function normalize(k, iso) {
        if (!iso || !range)
            return "";
        const today = range.today;
        if (k === "day" && iso >= today)
            return "";
        if (k === "week" && Fmt.mondayOf(iso) >= Fmt.mondayOf(today))
            return "";
        return iso;
    }

    function setKind(k) {
        if (k === kind)
            return;
        let a = anchor;
        if (k === "week")
            a = normalize("week", anchor);
        else if (anchor !== "" && range)
            a = normalize("day", range.end);   // last day of the viewed week
        detailAppId = "";
        kind = k;
        anchor = a;
        PluginService.setGlobalVar(pid, "lastKind", k);
    }

    function go(iso) {
        anchor = normalize(kind, iso);
    }

    function openDay(iso) {
        detailAppId = "";
        kind = "day";
        anchor = normalize("day", iso);
        PluginService.setGlobalVar(pid, "lastKind", "day");
    }

    onEntryChanged: {
        if (entry)
            shown = entry.data;
    }
    onKeyChanged: {
        if (entry)
            shown = entry.data;
        request(false);
        chart.replay();
    }

    Connections {
        target: root.parentPopout
        function onShouldBeVisibleChanged() {
            if (!root.parentPopout.shouldBeVisible)
                return;
            // Every open starts at the current period with fresh numbers.
            root.detailAppId = "";
            root.anchor = "";
            root.request(true);
            chart.replay();
        }
    }

    Component.onCompleted: {
        if (entry)
            shown = entry.data;
        request(true);
    }

    // -- labels --------------------------------------------------------------

    function rangeLabel() {
        if (!range)
            return kind === "day" ? tr("Today") : tr("This week");
        const loc = Qt.locale();
        if (kind === "day") {
            if (range.anchor === range.today)
                return tr("Today");
            if (range.anchor === Fmt.addDays(range.today, -1))
                return tr("Yesterday");
            const d = Fmt.parseDate(range.anchor);
            const sameYear = d.getFullYear() === Fmt.parseDate(range.today).getFullYear();
            return d.toLocaleDateString(loc, sameYear ? "ddd, d MMM" : "ddd, d MMM yyyy");
        }
        if (range.is_current)
            return tr("This week");
        if (range.start === Fmt.addDays(Fmt.mondayOf(range.today), -7))
            return tr("Last week");
        const s = Fmt.parseDate(range.start), e = Fmt.parseDate(range.end);
        const left = s.getMonth() === e.getMonth() ? s.toLocaleDateString(loc, "d") : s.toLocaleDateString(loc, "d MMM");
        return left + " – " + e.toLocaleDateString(loc, "d MMM");
    }

    function comparisonText() {
        if (!shown)
            return "";
        const pct = shown.vs_average_pct;
        if (kind === "day") {
            const avg = Fmt.duration(shown.average_seconds);
            if (pct === null || pct === undefined)
                return tr("No 7-day average yet");
            if (Math.abs(pct) < 5)
                return tr("About your 7-day average of %1").arg(avg);
            return (pct > 0 ? tr("%1 % above your 7-day average of %2") : tr("%1 % below your 7-day average of %2")).arg(Math.abs(pct)).arg(avg);
        }
        const perDay = tr("%1 per day").arg(Fmt.duration(shown.compare_seconds));
        if (pct === null || pct === undefined)
            return perDay;
        if (Math.abs(pct) < 5)
            return perDay + " · " + tr("about the same as the week before");
        return perDay + " · " + (pct > 0 ? tr("%1 % more than the week before") : tr("%1 % less than the week before")).arg(Math.abs(pct));
    }

    function chartBuckets() {
        if (!shown)
            return [];
        const loc = Qt.locale();
        const pad = n => (n < 10 ? "0" : "") + n;
        return shown.chart.buckets.map(b => {
            if (shown.chart.unit === "hour") {
                return {
                    seconds: b.seconds,
                    is_current: b.is_current,
                    is_future: b.is_future,
                    label: b.hour % 6 === 0 ? String(b.hour) : "",
                    tip: pad(b.hour) + ":00–" + pad((b.hour + 1) % 24) + ":00 · " + Fmt.duration(b.seconds)
                };
            }
            const d = Fmt.parseDate(b.date);
            return {
                seconds: b.seconds,
                is_current: b.is_current,
                is_future: b.is_future,
                label: loc.dayName(b.weekday % 7, Locale.ShortFormat),
                tip: d.toLocaleDateString(loc, "ddd, d MMM") + " · " + Fmt.duration(b.seconds),
                date: b.date
            };
        });
    }

    readonly property var stateInfo: {
        const s = shown?.daemon?.state ?? "stopped";
        switch (s) {
        case "active":
            return { text: tr("Live"), color: Theme.primary, live: true };
        case "idle":
            return { text: tr("Idle"), color: Theme.surfaceVariantText, live: false };
        case "locked":
        case "sleeping":
            return { text: tr("Paused"), color: Theme.surfaceVariantText, live: false };
        case "no_focus":
            return { text: tr("No app focused"), color: Theme.surfaceVariantText, live: false };
        default:
            return { text: tr("Not tracking"), color: Theme.error, live: false };
        }
    }

    // -- layout --------------------------------------------------------------

    headerText: tr("Screen Time")
    showCloseButton: false

    headerActions: Component {
        DankActionButton {
            iconName: "refresh"
            iconSize: Theme.iconSize - 6
            buttonSize: 32
            tooltipText: I18n.trFor("screenTime", "Refresh")
            onClicked: root.request(true)
        }
    }

    Column {
        width: parent.width
        spacing: Theme.spacingM

        // Day | Week, and the period navigator.
        Item {
            width: parent.width
            height: 40

            DankButtonGroup {
                id: kindGroup
                anchors.left: parent.left
                anchors.leftMargin: Theme.spacingS
                anchors.verticalCenter: parent.verticalCenter
                model: [root.tr("Day"), root.tr("Week")]
                currentIndex: root.kind === "week" ? 1 : 0
                onSelectionChanged: (index, selected) => {
                    if (selected)
                        root.setKind(index === 1 ? "week" : "day");
                }
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: Theme.spacingXS
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spacingXS

                DankActionButton {
                    anchors.verticalCenter: parent.verticalCenter
                    iconName: "chevron_left"
                    enabled: !!(root.range && root.range.prev)
                    opacity: enabled ? 1 : 0.38
                    onClicked: root.go(root.range.prev)
                }

                StyledText {
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(implicitWidth, 96)
                    horizontalAlignment: Text.AlignHCenter
                    text: root.rangeLabel()
                    font.pixelSize: Theme.fontSizeMedium
                    font.weight: Font.Medium
                    color: Theme.surfaceText
                }

                DankActionButton {
                    anchors.verticalCenter: parent.verticalCenter
                    iconName: "chevron_right"
                    enabled: !!(root.range && root.range.next)
                    opacity: enabled ? 1 : 0.38
                    onClicked: root.go(root.range.next)
                }
            }
        }

        Flickable {
            id: flick
            width: parent.width
            height: root.bodyHeight
            clip: true
            contentWidth: width
            contentHeight: (root.detailApp ? detailPage.implicitHeight : listPage.implicitHeight) + Theme.spacingS
            boundsBehavior: Flickable.StopAtBounds

            Behavior on contentHeight {
                NumberAnimation {
                    duration: Theme.shortDuration
                    easing.type: Theme.standardEasing
                }
            }

            // ---------------------------------------------------------- list page
            Column {
                id: listPage
                width: flick.width
                spacing: Theme.spacingM
                x: root.detailApp ? -width * 0.3 : 0
                opacity: root.detailApp ? 0 : 1
                visible: opacity > 0

                Behavior on x {
                    NumberAnimation {
                        duration: Theme.expressiveDurations.normal
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: Theme.expressiveCurves.emphasized
                    }
                }
                Behavior on opacity {
                    NumberAnimation {
                        duration: Theme.shortDuration
                    }
                }

                // Errors and first-run states replace the content.
                StEmptyState {
                    width: parent.width
                    visible: root.cli && root.cli.missing === true && !root.shown
                    icon: "terminal"
                    title: root.tr("Screen Time isn't installed")
                    body: root.tr("The plugin needs the screentime daemon and CLI. Run the installer from the screen-time repository.")
                    command: "./install.sh"
                }

                StEmptyState {
                    width: parent.width
                    visible: !!root.shown && !root.shown.daemon.running && root.shown.total_seconds === 0 && root.isCurrent
                    icon: "timer_off"
                    title: root.tr("The tracker isn't running")
                    body: root.tr("Start it to begin recording screen time.")
                    command: "systemctl --user enable --now screentime"
                }

                StEmptyState {
                    width: parent.width
                    visible: !!root.shown && root.shown.daemon.running && root.shown.total_seconds === 0 && !root.loading
                    icon: "hourglass_empty"
                    title: root.isCurrent ? root.tr("No screen time yet") : root.tr("No screen time recorded")
                    body: root.isCurrent ? root.tr("Usage shows up here as you use your apps.") : root.tr("Nothing was tracked in this period.")
                }

                // Warning banner when there is data but tracking stopped.
                Rectangle {
                    width: parent.width
                    height: 40
                    radius: Theme.cornerRadius
                    visible: !!root.shown && !root.shown.daemon.running && root.shown.total_seconds > 0
                    color: Theme.withAlpha(Theme.error, 0.12)

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.spacingM
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.spacingS

                        DankIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            name: "warning"
                            size: Theme.iconSizeSmall
                            color: Theme.error
                        }
                        StyledText {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.tr("Tracking is paused: the screentime service is not running")
                            font.pixelSize: Theme.fontSizeSmall
                            color: Theme.surfaceText
                        }
                    }
                }

                // Hero: total, comparison, chart.
                StCard {
                    id: hero
                    width: parent.width
                    visible: !root.shown || root.shown.total_seconds > 0 || !root.isCurrent || root.loading
                    pad: Theme.spacingL

                    Column {
                        width: parent.width
                        spacing: Theme.spacingM

                        Item {
                            width: parent.width
                            height: totalRow.height

                            Row {
                                id: totalRow
                                spacing: Theme.spacingS
                                opacity: root.shown ? 1 : 0.3

                                Repeater {
                                    model: Fmt.durationParts(root.shown ? root.shown.total_seconds : 0)

                                    Row {
                                        required property var modelData
                                        spacing: 3

                                        NumericText {
                                            id: bigNumber
                                            isMonospace: false
                                            text: modelData.value
                                            font.pixelSize: Theme.fontSizeXLarge * 2
                                            font.weight: Font.Medium
                                            color: Theme.surfaceText
                                        }
                                        StyledText {
                                            anchors.baseline: bigNumber.baseline
                                            text: modelData.unit
                                            font.pixelSize: Theme.fontSizeLarge
                                            font.weight: Font.Medium
                                            color: Theme.surfaceVariantText
                                        }
                                    }
                                }
                            }

                            // Live status chip (current period only).
                            Rectangle {
                                anchors.right: parent.right
                                anchors.top: parent.top
                                visible: root.isCurrent && !!root.shown
                                height: 26
                                width: chipRow.implicitWidth + Theme.spacingM * 2
                                radius: height / 2
                                color: Theme.withAlpha(root.stateInfo.color, 0.12)

                                Row {
                                    id: chipRow
                                    anchors.centerIn: parent
                                    spacing: Theme.spacingXS + 2

                                    Rectangle {
                                        id: dot
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 7
                                        height: 7
                                        radius: 3.5
                                        color: root.stateInfo.color

                                        SequentialAnimation on opacity {
                                            running: root.stateInfo.live && root.parentPopout && root.parentPopout.shouldBeVisible
                                            loops: Animation.Infinite
                                            onRunningChanged: if (!running) dot.opacity = 1
                                            NumberAnimation { to: 0.35; duration: 900; easing.type: Easing.InOutSine }
                                            NumberAnimation { to: 1; duration: 900; easing.type: Easing.InOutSine }
                                        }
                                    }
                                    StyledText {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: root.stateInfo.text
                                        font.pixelSize: Theme.fontSizeSmall
                                        font.weight: Font.Medium
                                        color: root.stateInfo.color
                                    }
                                }
                            }
                        }

                        Row {
                            spacing: Theme.spacingXS
                            visible: !!root.shown

                            DankIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                readonly property var pct: root.shown ? root.shown.vs_average_pct : null
                                visible: pct !== null && pct !== undefined && Math.abs(pct) >= 5
                                name: pct > 0 ? "trending_up" : "trending_down"
                                size: Theme.iconSizeSmall
                                color: Theme.surfaceVariantText
                            }
                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: root.comparisonText()
                                font.pixelSize: Theme.fontSizeSmall + 1
                                color: Theme.surfaceVariantText
                            }
                        }

                        StBarChart {
                            id: chart
                            width: parent.width
                            height: 150
                            buckets: root.chartBuckets()
                            unit: root.shown ? root.shown.chart.unit : "hour"
                            averageSeconds: root.kind === "week" && root.shown && root.shown.average_seconds > 0 ? root.shown.average_seconds : -1
                            interactive: root.kind === "week"
                            onActivated: index => root.openDay(buckets[index].date)
                        }
                    }
                }

                StCard {
                    width: parent.width
                    visible: !!root.shown && root.shown.categories.length > 0
                    title: root.tr("Categories")

                    StCategoryBar {
                        width: parent.width
                        categories: root.shown ? root.shown.categories : []
                    }
                }

                StCard {
                    width: parent.width
                    visible: appModel.count > 0
                    title: root.tr("Apps")
                    trailing: appModel.count === 1 ? root.tr("1 app") : root.tr("%1 apps").arg(appModel.count)

                    ListView {
                        id: appList
                        width: parent.width
                        height: contentHeight
                        interactive: false
                        spacing: Theme.spacingXS
                        model: ListModel {
                            id: appModel
                        }
                        add: ListViewTransitions.add
                        move: ListViewTransitions.move
                        displaced: ListViewTransitions.displaced

                        delegate: StAppRow {
                            width: appList.width
                            appId: model.appId
                            name: model.name
                            icon: model.icon
                            category: model.category
                            seconds: model.seconds
                            fraction: model.fraction
                            onClicked: root.detailAppId = model.appId
                        }
                    }
                }
            }

            // -------------------------------------------------------- detail page
            StAppDetail {
                id: detailPage
                width: flick.width
                x: root.detailApp ? 0 : width
                opacity: root.detailApp ? 1 : 0
                visible: opacity > 0
                app: root.detailApp
                kind: root.kind
                summary: root.shown
                rangeLabel: root.rangeLabel()
                onBack: root.detailAppId = ""

                Behavior on x {
                    NumberAnimation {
                        duration: Theme.expressiveDurations.normal
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: Theme.expressiveCurves.emphasized
                    }
                }
                Behavior on opacity {
                    NumberAnimation {
                        duration: Theme.shortDuration
                    }
                }
            }
        }
    }

    // Keep the ListModel in step with the data so rows animate when they reorder.
    function syncApps() {
        const list = shown ? shown.apps : [];
        const top = list.length ? Math.max(1, list[0].seconds) : 1;
        const ids = list.map(a => a.app_id);
        for (let i = appModel.count - 1; i >= 0; i--) {
            if (ids.indexOf(appModel.get(i).appId) < 0)
                appModel.remove(i);
        }
        for (let i = 0; i < list.length; i++) {
            const a = list[i];
            const props = {
                appId: a.app_id,
                name: a.name,
                icon: a.icon || "",
                category: a.category || "",
                seconds: a.seconds,
                fraction: a.seconds / top
            };
            let j = -1;
            for (let k = i; k < appModel.count; k++) {
                if (appModel.get(k).appId === a.app_id) {
                    j = k;
                    break;
                }
            }
            if (j < 0) {
                appModel.insert(i, props);
            } else {
                if (j !== i)
                    appModel.move(j, i, 1);
                appModel.set(i, props);
            }
        }
    }

    onShownChanged: syncApps()

}
