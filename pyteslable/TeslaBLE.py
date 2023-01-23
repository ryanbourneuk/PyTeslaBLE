# protobuf
import os
from pyteslable import VCSEC_pb2
# cryptography
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
# encoding
import binascii
# ble
import simplepyble
import asyncio
from bleak import BleakClient, BleakGATTCharacteristic
# regex
import re
# files
from os.path import exists
# time
import time

class BLE:
    def __init__(self, private_key_file=None):
        if private_key_file is None:
            private_key_file = "private_key.pem"
        if not exists(private_key_file):
            self.__private_key = ec.generate_private_key(
                ec.SECP256R1(), default_backend())
            # save the key
            pem = self.__private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
            with open("private_key.pem", 'wb') as pem_out:
                pem_out.write(pem)
            print("Generated private key")
        else:
            try:
                with open(private_key_file, "rb") as key_file:
                    self.__private_key = serialization.load_pem_private_key(
                        key_file.read(),
                        password=None,
                        backend=default_backend()
                    )
            except Exception as e:
                print(e)
                exit()

    def getPrivateKey(self):
        return self.__private_key

    def scan(self, time=5000):
        adapters = simplepyble.Adapter.get_adapters()

        if len(adapters) == 0:
            print("No adapters found")
        elif len(adapters) == 1:
            adapter = adapters[0]
        else:
            # Query the user to pick an adapter
            print("Please select an adapter:")
            for i, adapter in enumerate(adapters):
                print(f"{i}: {adapter.identifier()} [{adapter.address()}]")

            choice = int(input("Enter choice: "))
            adapter = adapters[choice]

        adapter.scan_for(time)
        peripherals = adapter.scan_get_results()
        tesla_vehicles = VehicleList()
        for i, peripheral in enumerate(peripherals):
            manufacturer_data = peripheral.manufacturer_data()
            if len(manufacturer_data) > 0 and manufacturer_data.get(76) is not None:
                tesla_vehicles.add(peripheral, self.__private_key)
        return tesla_vehicles

    def get_vehicle_by_name(self, name):
        return self.scan().getName(name)

    def get_vehicle_by_address(self, address):
        return self.scan().getAddress(address)

class VehicleList:
    def __init__(self):
        self.__vehicles = []

    def add(self, peripheral, private_key):
        self.__vehicles.append(
            Vehicle(peripheral, private_key))

    def getName(self, name):
        if not re.match("^S[a-f\d]{16}[A-F]$", name):
            print("Invalid name")
            return None
        for vehicle in self.__vehicles:
            if vehicle.name() == name:
                return vehicle
        return None

    def getAddress(self, address):
        for vehicle in self.__vehicles:
            if vehicle.address() == address:
                return vehicle
        return None

    def get(self, index):
        return self.__vehicles[index]

    def __len__(self):
        return len(self.__vehicles)

    def __getitem__(self, index):
        return self.__vehicles[index]

    def __str__(self):
        result = "["
        for vehicle in self.__vehicles:
            result += str(vehicle) + ", "
        if (len(result) > 1):
            result = result[:-2]
        return result + "]"

class Vehicle:
    def __init__(self, peripheral: BleakClient, private_key):
        if not exists(".tesladata"):
            os.mkdir(".tesladata")
        file_name = ".tesladata/" + peripheral.address + ".txt"
        self.file_name = file_name.replace(":", "")
        self.__peripheral = peripheral
        arr = self.getLineFromFile()
        self.__private_key = private_key
        self.__vehicle_key_str = arr[2]
        self.__counter = int(arr[1])
        self.__service = TeslaMsgService(self)
        self.__debug = False

    def __str__(self):
        return f"{self.name()} ({self.address()})"

    def debug(self):
        self.__debug = True

    def onStatusChange(self, func):
        self.__onStatusChange = func

    def setStatus(self, data):
        closure_status = data.closureStatuses
        lock_state = data.vehicleLockState
        print(lock_state)
        self.__locked = lock_state == 1
        self.__charge_port_open = closure_status.chargePort == 1
        self.__front_driver_door_open = closure_status.frontDriverDoor == 1
        self.__rear_driver_door_open = closure_status.rearDriverDoor == 1
        self.__front_passenger_door_open = closure_status.frontPassengerDoor == 1
        self.__rear_passenger_door_open = closure_status.rearPassengerDoor == 1
        self.__rear_trunk_open = closure_status.rearTrunk == 1
        self.__front_trunk_open = closure_status.frontTrunk == 1
        if self.__onStatusChange is not None:
            self.__onStatusChange(self)

    def status(self):
        return {
            "locked": self.__locked,
            "charge_port_open": self.__charge_port_open,
            "front_driver_door_open": self.__front_driver_door_open,
            "rear_driver_door_open": self.__rear_driver_door_open,
            "front_passenger_door_open": self.__front_passenger_door_open,
            "rear_passenger_door_open": self.__rear_passenger_door_open,
            "rear_trunk_open": self.__rear_trunk_open,
            "front_trunk_open": self.__front_trunk_open
        }

    def is_debug(self):
        return self.__debug

    def getLineFromFile(self):
        file_name = self.file_name
        if not exists(file_name):
            with open(file_name, 'w') as f:
                f.write(
                    "{} {} {}".format(self.__peripheral.address, 1, "null"))
                return [self.__peripheral.address, 1, "null"]
        # opens the file and reads the line
        with open(file_name, "r") as f:
            line = f.readline()
            return line.split()

    def updateFile(self):
        file_name = self.file_name
        # write the new lines back to the file
        with open(file_name, "w") as f:
            f.write(
                "{} {} {}".format(self.__peripheral.address, self.__counter, self.__vehicle_key_str))

    def address(self):
        return self.__peripheral.address

    def name(self):
        return self.__peripheral.name

    def counter(self):
        return self.__counter

    def setCounter(self, counter):
        self.__counter = counter
        self.updateFile()

    def private_key(self):
        return self.__private_key

    def vehicle_key_str(self):
        if self.__vehicle_key_str == "null" or len(self.__vehicle_key_str) < 10:
            return None
        return self.__vehicle_key_str

    def setVehicleKeyStr(self, vehicle_key):
        self.__vehicle_key_str = vehicle_key
        self.updateFile()

    async def connect(self):
        # For dev purposes, print out the service UUIDs
        for service in self.__peripheral.services:
            print("\nService:", service.uuid)
            for characteristic in service.characteristics:
                print(characteristic.properties, characteristic.uuid)

        await self.__peripheral.connect(timeout=15)
        await self.__peripheral.start_notify(TeslaUUIDs.CHAR_READ_UUID, self.handle_notify)

    async def disconnect(self):
        await self.__peripheral.stop_notify(TeslaUUIDs.CHAR_READ_UUID)
        await self.__peripheral.disconnect()

    async def whitelist(self):
        msg = self.__service.whitelistMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)
        print("Sent whitelist request")
        while True:
            msg = self.__service.vehiclePublicKeyMsg()
            msg = bytes(msg)
            await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg, True)
            print("Waiting for keycard to be tapped...\n")
            time.sleep(2)  # I think time.sleep is not what I want
            if (self.isAdded()):
                print("Authorized successfully")
                break

    async def openDriversDoor(self):
        msg = self.__service.openDriversDoorMsg()
        msg = bytes(msg)
        self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def unlock(self):
        msg = self.__service.unlockMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def lock(self):
        msg = self.__service.lockMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg, True)

    async def open_trunk(self):
        msg = self.__service.openTrunkMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def open_frunk(self):
        msg = self.__service.openFrunkMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def open_charge_port(self):
        msg = self.__service.openChargePortMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def close_charge_port(self):
        msg = self.__service.closeChargePortMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def vehicle_status(self):
        msg = self.__service.vehicleStatusMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    async def vehicle_info(self):
        msg = self.__service.vehicleInfoMsg()
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg)

    def isAdded(self):
        return self.__service.isAdded()

    def isConnected(self):
        return self.__peripheral.is_connected

    async def handle_notify(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        await self.__service.handle_notify(data)

    async def authenticationRequest(self, requested_level):
        msg = self.__service.authenticationRequestMsg(requested_level)
        msg = bytes(msg)
        await self.__peripheral.write_gatt_char(TeslaUUIDs.CHAR_WRITE_UUID, msg, True) # TODO: try this as false?


class TeslaMsgService:
    def __init__(self, vehicle):
        self.__vehicle = vehicle
        self.setCounter(vehicle.counter())
        self.vehicle_key = None
        self.private_key = vehicle.private_key()
        vehicle_key_str = vehicle.vehicle_key_str()
        if vehicle_key_str is not None:
            self.loadEphemeralKey(vehicle_key_str)

    def __str__(self):
        return "BLE Address: {}, Name: {}".format(self.__vehicle.address(), self.__vehicle.name())

    def vehicle(self):
        return self.__vehicle

    def isAdded(self):
        return self.vehicle_key != None

    def getPrivateKey(self):
        private_key_bytes = self.__vehicle.private_key().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        return private_key_bytes

    def getPublicKey(self):
        public_key_bytes = self.__vehicle.private_key().public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        return public_key_bytes

    def getKeyId(self):
        public_key = self.getPublicKey()

        digest = hashes.Hash(hashes.SHA1())
        digest.update(public_key)
        return digest.finalize()[:4]

    def getSharedKey(self):
        # creates sha1 hasher for creating shared key
        hasher = hashes.Hash(hashes.SHA1())
        # exchange own private key with car's ephemeral key to create an intermediate shared key
        shared_key = self.private_key.exchange(
            ec.ECDH(), self.vehicle_key)
        # intermediate shared key is then inserted into the hasher
        hasher.update(shared_key)
        # and the first 16 bytes of the hash will be our final shared key
        return hasher.finalize()[:16]

    def signedToMsg(self, message):
        if not self.isAdded():
            raise Exception('Car\'s ephermeral key not yet loaded!')
        shared_secret = self.getSharedKey()
        encryptor = AESGCM(shared_secret)
        nonce = bytearray()
        nonce.append((self.counter >> 24) & 255)
        nonce.append((self.counter >> 16) & 255)
        nonce.append((self.counter >> 8) & 255)
        nonce.append(self.counter & 255)

        print("sending message: ", message, self.counter)

        umsg_to = VCSEC_pb2.ToVCSECMessage()
        umsg_to.unsignedMessage.CopyFrom(message)

        encrypted_msg = encryptor.encrypt(
            nonce,
            umsg_to.SerializeToString(),
            None
        )

        msg = VCSEC_pb2.ToVCSECMessage()
        signed_msg = msg.signedMessage
        signed_msg.protobufMessageAsBytes = encrypted_msg[:-16]
        signed_msg.signatureType = VCSEC_pb2.SIGNATURE_TYPE_AES_GCM
        signed_msg.counter = self.counter
        signed_msg.signature = encrypted_msg[-16:]
        signed_msg.keyId = self.getKeyId()

        self.setCounter(self.counter + 1)
        return self.prependLength(msg.SerializeToString())

    def unsignedToMsg(self, message):
        msg = VCSEC_pb2.ToVCSECMessage()
        unsigned_msg = msg.unsignedMessage
        unsigned_msg.CopyFrom(message)
        return self.prependLength(msg.SerializeToString())

    def prependLength(self, message):
        return bytearray([len(message) >> 8, len(message) & 0xFF]) + message

    def loadEphemeralKey(self, key):
        if isinstance(key, str):
            key = key[2:-1]
            key = binascii.unhexlify(key)
        self.ephemeral_str = binascii.hexlify(key)
        curve = ec.SECP256R1()
        self.vehicle_key = ec.EllipticCurvePublicKey.from_encoded_point(
            curve, key)
        self.__vehicle.setVehicleKeyStr(self.ephemeral_str)

    def setCounter(self, counter):
        self.counter = counter
        self.__vehicle.setCounter(counter)

    ###########################       PROCESS RESPONSES       #############################

    async def handle_notify(self, data: bytearray):
        # remove first two bytes (length)
        data = data[2:]
        msg = VCSEC_pb2.FromVCSECMessage()
        msg.ParseFromString(data)

        if self.__vehicle.is_debug():
            print("received data", msg)

        # see if the response is the shared key
        if msg.HasField('sessionInfo'):
            key = msg.sessionInfo.publicKey
            self.loadEphemeralKey(key)
            print("Loaded ephemeral key")
        elif msg.HasField('authenticationRequest'):
            await self.__vehicle.authenticationRequest(
                msg.authenticationRequest.requestedLevel)
        elif msg.HasField('vehicleStatus'):
            self.__vehicle.setStatus(msg.vehicleStatus)

        # TODO: check if the message is signed
        # TODO: get command status
        # TODO: do something with the message
        return True

    ###########################       VEHICLE ACTIONS       #############################

    # These functions generate a message to perform a particular action, such
    # as unlocking the vehicle. The response is in the form of a byte array.
    # Note: It still needs to be encrypted and prepended.

    def whitelistMsg(self):
        # request to add a vehicle to the whitelist, request permissions
        msg = VCSEC_pb2.UnsignedMessage()
        whitelist_operation = msg.WhitelistOperation
        permissions_action = whitelist_operation.addKeyToWhitelistAndAddPermissions
        print(permissions_action)
        #.addKeyToWhitelistAndAddPermissions
        permissions_action.key.PublicKeyRaw = self.getPublicKey()
        permissions = permissions_action.permission
        permissions.append(VCSEC_pb2.WHITELISTKEYPERMISSION_LOCAL_DRIVE)
        permissions.append(VCSEC_pb2.WHITELISTKEYPERMISSION_LOCAL_UNLOCK)
        permissions.append(VCSEC_pb2.WHITELISTKEYPERMISSION_REMOTE_DRIVE)
        permissions.append(VCSEC_pb2.WHITELISTKEYPERMISSION_REMOTE_UNLOCK)
        whitelist_operation.metadataForKey.keyFormFactor = VCSEC_pb2.KEY_FORM_FACTOR_ANDROID_DEVICE

        print("whitelistMsg", msg.SerializeToString())
        msg2 = VCSEC_pb2.ToVCSECMessage()
        msg2.signedMessage.signatureType = VCSEC_pb2.SIGNATURE_TYPE_PRESENT_KEY
        msg2.signedMessage.protobufMessageAsBytes = msg.SerializeToString()
        return self.prependLength(msg2.SerializeToString())

    def unlockMsg(self):
        # unlocks the vehicle
        return self.rkeActionMsg(VCSEC_pb2.RKEAction_E.RKE_ACTION_UNLOCK)

    def lockMsg(self):
        return self.rkeActionMsg(VCSEC_pb2.RKEAction_E.RKE_ACTION_LOCK)

    def openTrunkMsg(self):
        # opens the rear trunk
        return self.rkeActionMsg(VCSEC_pb2.RKEAction_E.RKE_ACTION_OPEN_TRUNK)

    def openFrunkMsg(self):
        # opens the front trunk
        return self.rkeActionMsg(VCSEC_pb2.RKEAction_E.RKE_ACTION_OPEN_FRUNK)

    def openChargePortMsg(self):
        # opens the charge port
        return self.rkeActionMsg(VCSEC_pb2.RKEAction_E.RKE_ACTION_OPEN_CHARGE_PORT)

    def closeChargePortMsg(self):
        # closes the charge port
        return self.rkeActionMsg(VCSEC_pb2.RKEAction_E.RKE_ACTION_CLOSE_CHARGE_PORT)

    def openDriversDoorMsg(self):
        return self.closureMoveRequestMsg(VCSEC_pb2.ClosureMoveRequest.frontDriverDoor)

    def rkeActionMsg(self, action):
        # executes the given RKE action
        msg = VCSEC_pb2.UnsignedMessage()
        msg.RKEAction = action
        return self.signedToMsg(msg)

    def closureMoveRequestMsg(self, action):
        msg = VCSEC_pb2.UnsignedMessage()
        msg.closureMoveRequest = action
        return self.signedToMsg(msg)

    def informationRequestMsg(self, type):
        # requests information about the vehicle
        msg = VCSEC_pb2.UnsignedMessage()
        info_request = msg.InformationRequest
        info_request.informationRequestType = type
        key_id = info_request.keyId
        key_id.publicKeySHA1 = self.getKeyId()
        return self.signedToMsg(msg)

    def vehicleInfoMsg(self):
        return self.informationRequestMsg(VCSEC_pb2.INFORMATION_REQUEST_TYPE_GET_VEHICLE_INFO)

    def vehicleStatusMsg(self):
        return self.informationRequestMsg(VCSEC_pb2.INFORMATION_REQUEST_TYPE_GET_STATUS)

    def authenticationRequestMsg(self, level):
        msg = VCSEC_pb2.UnsignedMessage()
        msg.authenticationResponse.authenticationLevel = level
        return self.signedToMsg(msg)

    def vehiclePublicKeyMsg(self):
        # requests the public key of the vehicle
        msg = VCSEC_pb2.UnsignedMessage()
        info_request = msg.InformationRequest
        info_request.informationRequestType = VCSEC_pb2.INFORMATION_REQUEST_TYPE_GET_EPHEMERAL_PUBLIC_KEY
        key_id = info_request.keyId
        key_id.publicKeySHA1 = self.getKeyId()
        return self.unsignedToMsg(msg)


class TeslaUUIDs:
    SERVICE_UUID = "00000211-b2d1-43f0-9b88-960cebf8b91e"       # Tesla Vehicle Service
    CHAR_WRITE_UUID = "00000212-b2d1-43f0-9b88-960cebf8b91e"    # To Vehicle
    CHAR_READ_UUID = "00000213-b2d1-43f0-9b88-960cebf8b91e"     # From Vehicle
    CHAR_VERSION_UUID = "00000214-b2d1-43f0-9b88-960cebf8b91e"  # Version Info
