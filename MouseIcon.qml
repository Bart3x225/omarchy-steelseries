import QtQuick

// Font-independent mouse silhouette; follows the bar's current theme.
Item {
    id: root
    property color color: "white"
    width: 20
    height: 24
    Rectangle {
        id: body
        width: 16; height: 22
        anchors.centerIn: parent
        radius: 8
        color: "transparent"
        border.color: root.color
        border.width: 1.6
        Rectangle {
            width: 2; height: 5; radius: 1
            anchors.horizontalCenter: parent.horizontalCenter
            y: 4
            color: root.color
        }
        Rectangle {
            width: 1.2; height: 3
            anchors.horizontalCenter: parent.horizontalCenter
            y: 1
            color: root.color
        }
    }
}
