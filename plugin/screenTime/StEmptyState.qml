import QtQuick
import qs.Common
import qs.Widgets

// Friendly empty / error state: tonal icon disc, title, body and an optional
// command hint shown in a monospace chip.
Column {
    id: root

    property string icon: "timelapse"
    property string title: ""
    property string body: ""
    property string command: ""

    spacing: Theme.spacingM
    topPadding: Theme.spacingXL
    bottomPadding: Theme.spacingXL

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 72
        height: 72
        radius: 36
        color: Theme.withAlpha(Theme.primary, 0.12)

        DankIcon {
            anchors.centerIn: parent
            name: root.icon
            size: 36
            color: Theme.primary
        }
    }

    StyledText {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: root.title
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.DemiBold
        color: Theme.surfaceText
        wrapMode: Text.WordWrap
    }

    StyledText {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        visible: root.body !== ""
        text: root.body
        font.pixelSize: Theme.fontSizeMedium
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }

    Rectangle {
        visible: root.command !== ""
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width, cmdText.implicitWidth + Theme.spacingL * 2)
        height: cmdText.implicitHeight + Theme.spacingS * 2
        radius: Theme.cornerRadius
        color: Theme.withAlpha(Theme.surfaceText, 0.06)

        StyledText {
            id: cmdText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, parent.width - Theme.spacingL * 2)
            elide: Text.ElideRight
            text: root.command
            isMonospace: true
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceText
        }
    }
}
