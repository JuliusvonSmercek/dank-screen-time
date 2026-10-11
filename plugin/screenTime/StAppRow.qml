import QtQuick
import qs.Common
import qs.Widgets
import "StFormat.js" as Fmt

// One ranked app: icon, name + category, duration, proportional bar.
Item {
    id: root

    property string appId: ""
    property string name: ""
    property string icon: ""
    property string category: ""
    property real seconds: 0
    property real fraction: 0       // relative to the top app (top app = 1)
    property bool compact: false

    signal clicked

    implicitHeight: compact ? 40 : 56

    Rectangle {
        id: hoverBg
        anchors.fill: parent
        anchors.leftMargin: -Theme.spacingS
        anchors.rightMargin: -Theme.spacingS
        radius: Theme.cornerRadius
        color: mouse.containsMouse ? Theme.surfaceTextHover : Theme.withAlpha(Theme.surfaceTextHover, 0)

        Behavior on color {
            ColorAnimation {
                duration: Theme.shorterDuration
            }
        }

        DankRipple {
            id: ripple
            cornerRadius: Theme.cornerRadius
            rippleColor: Theme.surfaceText
        }
    }

    StAppIcon {
        id: appIcon
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        iconSize: root.compact ? 24 : 36
        appId: root.appId
        icon: root.icon
        name: root.name
    }

    Item {
        anchors.left: appIcon.right
        anchors.leftMargin: Theme.spacingM
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: textCol.height

        Column {
            id: textCol
            width: parent.width
            spacing: root.compact ? 4 : 6

            Item {
                width: parent.width
                height: nameText.implicitHeight

                StyledText {
                    id: nameText
                    anchors.left: parent.left
                    anchors.right: durationText.left
                    anchors.rightMargin: Theme.spacingS
                    text: root.name
                    elide: Text.ElideRight
                    font.pixelSize: root.compact ? Theme.fontSizeSmall : Theme.fontSizeMedium
                    font.weight: Font.Medium
                    color: Theme.surfaceText
                }

                NumericText {
                    id: durationText
                    anchors.right: parent.right
                    anchors.verticalCenter: nameText.verticalCenter
                    isMonospace: false
                    text: Fmt.duration(root.seconds)
                    font.pixelSize: root.compact ? Theme.fontSizeSmall : Theme.fontSizeMedium
                    color: Theme.surfaceVariantText
                }
            }

            Item {
                width: parent.width
                height: 6

                Rectangle {
                    id: barTrack
                    anchors.left: parent.left
                    anchors.right: categoryText.visible ? categoryText.left : parent.right
                    anchors.rightMargin: categoryText.visible ? Theme.spacingM : 0
                    anchors.verticalCenter: parent.verticalCenter
                    height: root.compact ? 4 : 6
                    radius: height / 2
                    color: Theme.withAlpha(Theme.primary, 0.12)

                    Rectangle {
                        height: parent.height
                        radius: parent.radius
                        width: Math.max(height, parent.width * Math.min(1, root.fraction))
                        color: Theme.primary

                        Behavior on width {
                            NumberAnimation {
                                duration: Theme.mediumDuration
                                easing.type: Easing.BezierSpline
                                easing.bezierCurve: Theme.expressiveCurves.emphasizedDecel
                            }
                        }
                    }
                }

                StyledText {
                    id: categoryText
                    visible: !root.compact && root.category !== ""
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, parent.width * 0.4)
                    elide: Text.ElideRight
                    text: root.category
                    font.pixelSize: Theme.fontSizeSmall - 1
                    color: Theme.surfaceVariantText
                }
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: hoverBg
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onPressed: m => ripple.trigger(m.x, m.y)
        onClicked: root.clicked()
    }
}
