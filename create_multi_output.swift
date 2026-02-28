import CoreAudio
import Foundation

// MARK: - Helpers

func getPropertyDataSize(_ objectID: AudioObjectID, _ selector: AudioObjectPropertySelector) -> UInt32 {
    var addr = AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(objectID, &addr, 0, nil, &size)
    return size
}

func getDeviceUIDs() -> [(id: AudioObjectID, name: String, uid: String, outputChannels: UInt32)] {
    var addr = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size = getPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDevices)
    let count = Int(size) / MemoryLayout<AudioObjectID>.size
    var deviceIDs = [AudioObjectID](repeating: 0, count: count)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &deviceIDs)

    var results: [(id: AudioObjectID, name: String, uid: String, outputChannels: UInt32)] = []

    for devID in deviceIDs {
        // Name
        var nameAddr = AudioObjectPropertyAddress(
            mSelector: kAudioObjectPropertyName,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var name: CFString = "" as CFString
        var nameSize = UInt32(MemoryLayout<CFString>.size)
        AudioObjectGetPropertyData(devID, &nameAddr, 0, nil, &nameSize, &name)

        // UID
        var uidAddr = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceUID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var uid: CFString = "" as CFString
        var uidSize = UInt32(MemoryLayout<CFString>.size)
        AudioObjectGetPropertyData(devID, &uidAddr, 0, nil, &uidSize, &uid)

        // Output channels
        var outputAddr = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamConfiguration,
            mScope: kAudioObjectPropertyScopeOutput,
            mElement: kAudioObjectPropertyElementMain
        )
        var bufSize: UInt32 = 0
        AudioObjectGetPropertyDataSize(devID, &outputAddr, 0, nil, &bufSize)
        let bufferListPtr = UnsafeMutablePointer<AudioBufferList>.allocate(capacity: Int(bufSize))
        defer { bufferListPtr.deallocate() }
        AudioObjectGetPropertyData(devID, &outputAddr, 0, nil, &bufSize, bufferListPtr)
        var outputCh: UInt32 = 0
        let bufferList = UnsafeMutableAudioBufferListPointer(bufferListPtr)
        for buf in bufferList {
            outputCh += buf.mNumberChannels
        }

        results.append((id: devID, name: name as String, uid: uid as String, outputChannels: outputCh))
    }
    return results
}

// MARK: - Main

let devices = getDeviceUIDs()

// Find speakers and BlackHole
var speakerUID: String?
var blackholeUID: String?

for dev in devices {
    let lower = dev.name.lowercased()
    if lower.contains("speaker") && dev.outputChannels > 0 {
        speakerUID = dev.uid
        print("Found speakers: \(dev.name) [\(dev.uid)]")
    }
    if lower == "blackhole 2ch" {
        blackholeUID = dev.uid
        print("Found BlackHole: \(dev.name) [\(dev.uid)]")
    }
}

guard let spkUID = speakerUID else {
    print("ERROR: Could not find MacBook Pro Speakers")
    exit(1)
}
guard let bhUID = blackholeUID else {
    print("ERROR: Could not find BlackHole 2ch")
    exit(1)
}

// Check if multi-output already exists
for dev in devices {
    if dev.name == "Multi-Output Device" {
        print("Multi-Output Device already exists (ID: \(dev.id)). Skipping creation.")
        exit(0)
    }
}

// Create multi-output device (stacked aggregate)
let desc: NSDictionary = [
    kAudioAggregateDeviceUIDKey: "com.standupbot.MultiOutputDevice",
    kAudioAggregateDeviceNameKey: "Multi-Output Device",
    kAudioAggregateDeviceSubDeviceListKey: [
        [kAudioSubDeviceUIDKey: spkUID],
        [kAudioSubDeviceUIDKey: bhUID],
    ],
    kAudioAggregateDeviceMainSubDeviceKey: spkUID,
    kAudioAggregateDeviceIsStackedKey: 1,
]

var aggregateID: AudioObjectID = 0
let status = AudioHardwareCreateAggregateDevice(desc, &aggregateID)

if status == noErr {
    print("Created Multi-Output Device (ID: \(aggregateID))")
} else {
    print("ERROR: Failed to create Multi-Output Device (OSStatus: \(status))")
    exit(1)
}
