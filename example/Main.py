from pyteslable import BLE
from pyteslable import Vehicle
import asyncio
from bleak import BleakScanner, BleakClient

async def main():
    tesla_ble = BLE("private_key.pem")
    private_key = tesla_ble.getPrivateKey()

    # TODO: Move scanning logic back to BLE client

    print("\nStarted PyTeslaBLE!\n")
    print("Scanning for devices...\n")

    devices = await BleakScanner.discover() # TODO: Look at filtering with service_uuids to only find the Tesla device.
    filteredDevices = list(filter(lambda x: x.name != None, devices))

    if (len(filteredDevices)) == 0:
        print("No devices found")
        exit()

    print("Select a device:")
    for i, device in enumerate(filteredDevices):
        print(i, device.address, device.name)

    choice = int(input("Enter choice: "))
    device = filteredDevices[choice]

    async with BleakClient(device.address) as client:
        vehicle = Vehicle(client, private_key)

        # now we can connect to the vehicle
        if (vehicle == None):
            print("Vehicle not found")
            exit()

        print("Connecting to vehicle...")
        await vehicle.connect()
        vehicle.debug()

        if not vehicle.isConnected():
            print("Vehicle failed to connect")
            exit()

        if not vehicle.isAdded():
            print("Tap your keycard on the center console")
            await vehicle.whitelist()
        
        # Print closure status of all doors when they change
        vehicle.onStatusChange(lambda vehic: print(f"\nStatus update: {vehic.status()}\n"))

        # Request status
        await vehicle.vehicle_status()

        command = ""
        while True:
            print("Enter a command, or 'help' for a list of commands. Type 'exit' to quit.")
            command = input("Enter command: ")
            command = command.upper().replace(' ', '_')
            if command == "LOCK":
                await vehicle.lock()
            elif command == "UNLOCK":
                await vehicle.unlock()
            elif command == "OPEN_TRUNK":
                await vehicle.open_trunk()
            elif command == "OPEN_FRUNK":
                await vehicle.open_frunk()
            elif command == "DOOR":
                # TODO: rename func to match python naming conventions.
                await vehicle.openDriversDoor()
            elif command == "OPEN_CHARGE_PORT":
                await vehicle.open_charge_port()
            elif command == "CLOSE_CHARGE_PORT":
                await vehicle.close_charge_port()
            elif command == "EXIT":
                break
            elif command == "HELP":
                print("\n\n\nCommands available:")
                print("\tEXIT: Exit the program")
                print("\tHELP: Print this message")
                print("\tLOCK: Lock the vehicle")
                print("\tUNLOCK: Unlock the vehicle")
                print("\tOPEN_TRUNK: Open the vehicle's trunk")
                print("\tOPEN_FRUNK: Open the vehicle's front trunk")
                print("\tOPEN_CHARGE_PORT: Open and unlock the vehicle's charge port")
                print("\tCLOSE_CHARGE_PORT: Close and lock the vehicle's charge port")
                print("\n\n")
            else:
                print("Unknown command")
        print("Disconnecting...")
        await vehicle.disconnect()
        print("Vehicle disconnected successfully")

asyncio.run(main())