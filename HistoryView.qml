import QtQuick
import qs.Commons
import qs.Commons as Commons
Item {
    id:root
    property var device: ({})
    readonly property var summary:device.history||{points:[],estimateMinutes:-1,estimateSamples:0}
    readonly property var points:summary.points||[]
    implicitHeight:column.implicitHeight
    Commons.Translations {id:strings;directory:Qt.resolvedUrl("i18n")}
    onPointsChanged:graph.requestPaint()
    Column {
        id:column;width:parent.width;spacing:Style.space(12)
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("historyRetention");color:Color.foreground;font.pixelSize:Style.font.body}
        Canvas {
            id:graph;width:parent.width;height:Style.space(160)
            onPaint:{
                var ctx=getContext("2d");ctx.reset();var pad=8,w=width-2*pad,h=height-2*pad;
                ctx.strokeStyle=Qt.alpha(Color.foreground,0.25);ctx.lineWidth=1;
                [0,0.5,1].forEach(function(y){ctx.beginPath();ctx.moveTo(pad,pad+y*h);ctx.lineTo(pad+w,pad+y*h);ctx.stroke()});
                if(!root.points.length)return;
                var first=root.points[0].ts,last=root.points[root.points.length-1].ts,span=Math.max(1,last-first);
                ctx.strokeStyle=Color.foreground;ctx.lineWidth=2;ctx.beginPath();
                root.points.forEach(function(p,i){var x=pad+(p.ts-first)/span*w,y=pad+h*(1-p.battery/100);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke();
                root.points.forEach(function(p){var x=pad+(p.ts-first)/span*w,y=pad+h*(1-p.battery/100);ctx.beginPath();ctx.arc(x,y,2,0,Math.PI*2);ctx.fillStyle=p.charging?Color.urgent:Color.foreground;ctx.fill()});
            }
        }
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:root.points.length?strings.t("historySamples").arg(root.points.length):strings.t("historyEmpty");color:Color.foreground;font.pixelSize:Style.font.body}
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:root.summary.estimateMinutes>=0?strings.t("estimate").arg(Math.round(root.summary.estimateMinutes)):strings.t("estimatePending");color:Color.foreground;font.pixelSize:Style.font.body}
    }
}
