pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import "FleetModel.js" as Model

Item {
    id: root
    property var snapshot: ({devices:[],updated:0})
    property var config: ({pollSeconds:5,lowThreshold:20,criticalThreshold:5,notifyLow:true,notifyCritical:true,notifyFull:true,notifyConnections:true,hiddenIds:[],historyDays:30,experimentalControls:false})
    property var transitionState: null
    property string error: ""
    property var operationResult: ({})
    property int retryCount: 0
    readonly property bool busy: probe.running || operation.running
    Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
    function command(args) { return ["/usr/bin/python","-B",Qt.resolvedUrl("app.py").toString().replace("file://","")].concat(args) }
    function refresh() { if(!root.busy) probe.running=true }
    function runOperation(args) {
        if(root.busy) { root.operationResult={ok:false,error:strings.t("busy")};return false }
        root.operationResult={};operation.command=root.command(args);operation.running=true;return true
    }
    function saveConfig(values) { return root.runOperation(["save-settings",JSON.stringify(values)]) }
    function applyDevice(id,values) { return root.runOperation(["apply",id,JSON.stringify(values)]) }
    Process {
        id: probe
        command: root.command(["snapshot"])
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var value=JSON.parse(text)
                    if(!Array.isArray(value.devices)||value.devices.length>64)throw new Error(value.error||"Invalid inventory")
                    if(value.config && JSON.stringify(root.config)!==JSON.stringify(value.config))root.config=value.config
                    root.transitionState=Model.advance(root.transitionState,value.devices,Object.assign({},root.config,{confirmations:2,inventoryComplete:Object.keys(value.source_errors||{}).length===0}))
                    root.snapshot=value;root.error="";root.retryCount=0
                    root.transitionState.events.forEach(function(event) {
                        var message=(event.type==="low"||event.type==="critical")?strings.t(event.type).arg(event.device.battery):strings.t("notify."+event.type)
                        Quickshell.execDetached(["notify-send","--app-name=SteelSeries","--icon=input-gaming","--urgency="+(event.type==="critical"?"critical":"normal"),Model.safeText(event.device.name),message])
                    })
                } catch(e) { root.error=String(e).slice(0,400);if(root.retryCount<1){root.retryCount++;retry.start()} }
            }
        }
    }
    Process {
        id: operation
        stdout: StdioCollector {
            onStreamFinished: {
                try { root.operationResult=JSON.parse(text);if(root.operationResult.config)root.config=root.operationResult.config }
                catch(e){root.operationResult={ok:false,error:"Invalid operation response"}}
            }
        }
        onExited: Qt.callLater(root.refresh)
    }
    Timer { id: retry;interval:1500;onTriggered:root.refresh() }
    Timer { interval:Math.max(2,Number(root.config.pollSeconds||5))*1000;repeat:true;running:true;triggeredOnStart:true;onTriggered:root.refresh() }
    Commons.ShellIpc {
        target:"bart.steelseries.status"
        function status(): string {return JSON.stringify({devices:root.snapshot.devices,updated:root.snapshot.updated,error:root.error,source_errors:root.snapshot.source_errors||{},config:root.config,operation:root.operationResult})}
        function refresh(): string {root.refresh();return "ok"}
        function saveSettings(value: string): string {try{return root.saveConfig(JSON.parse(value))?"ok":"busy"}catch(e){return "invalid"}}
    }
}
