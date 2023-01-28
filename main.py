from enum import Enum
from fastapi import FastAPI
import uvicorn
from licensing.models import *
from licensing.methods import Key, Helpers, Data
import os
from dotenv import load_dotenv
import uuid

from timeloop import Timeloop
from datetime import timedelta

load_dotenv()

tl = Timeloop()

# Generate unique machine code on app startup
machine_code = uuid.uuid4().hex

# check license after this interval
license_interval_seconds = 100

# Up front usage count limit
license_up_front_calls = 10


# TODO: access to the variable needs to be atomic, since modifying the data object does not update
licenseKey: LicenseKey


class Features(Enum):
    FEATURE1 = "f1"
    FEATURE2 = "f2"
    FEATURE3 = "f3"
    FEATURE4 = "f4"
    FEATURE5 = "f5"
    FEATURE6 = "f6"
    FEATURE7 = "f7"
    FEATURE8 = "f8"


# application/product specific names for the data object
class DataObjectNames(Enum):
    MIX_FEAT_USAGE_COUNT = "feat_mix_usage_count"
    MIX_FEAT_QUOTA_COUNT = "feat_mix_quota_count"
    FEAT1_USAGE_COUNT = "feat1_usage_count"


# =================================================
# Console Messages
# =================================================


licenseQuotaConsumed = {
    "message": "quota for the given license was consumed. Cannot perform more requests"
}

featureBlocked = {
    "message": "This feature is not enabled on provided application license"
}

licenseNotEnabled = {
    "message": "Error: License cannot be enabled! Please check the provided license key"
}

licenseUsed = {
    "message": "License cannot be enabled on this device. Maximum number of instances already running"
}


class ProgramKilled(Exception):
    pass


def signal_handler(signum, frame):
    print("signal handler called")
    raise ProgramKilled

# =================================================
# Application Server
# =================================================


def shutdown():
    tl.stop()
    licenseDeactivate()


app = FastAPI(
    title="{}".format(os.environ.get("HOSTNAME", "Flask APP")),
    on_shutdown=[shutdown])


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/feat1")
async def feat1():
    if (isFeatureEnabled(Features.FEATURE1)):
        return {"message": "Hello World from feature 1"}
    return featureBlocked


@app.get("/feat2")
async def feat2():

    if (isFeatureEnabled(Features.FEATURE2)):
        return {"message": "Hello World from feature 2"}
    return featureBlocked


@app.get("/feat-mix")
async def feat_mix():

    if (isFeatureEnabled(Features.FEATURE3) or isFeatureEnabled(Features.FEATURE4) or isFeatureEnabled(Features.FEATURE5)):
        return {"message": "Hello World from feature mix"}
    return featureBlocked


@app.get("/feat-mix-usage")
async def featMix_up_usage():

    if (isFeatureEnabled(Features.FEATURE3) or isFeatureEnabled(Features.FEATURE4) or isFeatureEnabled(Features.FEATURE5)):
        increment_object(DataObjectNames.MIX_FEAT_USAGE_COUNT)
        return {"message": "Hello World from feature mix usage based"}
    return featureBlocked


@app.get("/feat-mix-upfront")
async def featMix_up_front():
    objectName = DataObjectNames.MIX_FEAT_QUOTA_COUNT
    if (isFeatureEnabled(Features.FEATURE3) or isFeatureEnabled(Features.FEATURE4) or isFeatureEnabled(Features.FEATURE5)):
        if isQuotaAvailable(objectName):
            # we do some processing here
            decrement_object(objectName)
            return {"message": "Hello World from feature mix quota based"}
        else:
            return licenseQuotaConsumed
    return featureBlocked


# =================================================
# Cryptolens related calls
# =================================================


# returns error message otherwise None
@tl.job(interval=timedelta(seconds=license_interval_seconds))
def licenseCheck():
    # needs to be stored in the output build/docker image. should be readonly to the app user
    RSAPubKey = os.environ.get("CL_RSA_PUB_KEY", "")
    # only put auth token with the permission to activate a key. Since this will be shared with the clients in the build,
    # so we don't want to give access token with other permissions. https://help.cryptolens.io/faq/index#access-token
    # baked in the build/docker image. should be readonly to the app user
    auth = os.environ.get("CL_AUTH_TOKEN", "")
    # baked in the build/docker image. should be readonly to the app user
    productId = os.environ.get("CL_PRODUCT_ID", "")

    # provided by customer as env
    productKey = os.environ.get("CL_PRODUCT_KEY", "")

    # for containers we need to generate random string on application startup
    # https://help.cryptolens.io/licensing-models/containers
    result = Key.activate(token=auth,
                          rsa_pub_key=RSAPubKey,
                          product_id=productId,
                          key=productKey,
                          machine_code=machine_code,
                          floating_time_interval=license_interval_seconds)
    global licenseKey
    if result[0] == None:
        # an error occurred or the key is invalid or it cannot be activated
        # (eg. the limit of activated devices was achieved)
        print("The license does not work: {0}".format(result[1]))
        licenseKey = None
        # exit(1)
        return licenseNotEnabled
    elif not Helpers.IsOnRightMachine(result[0], v=2, is_floating_license=True, custom_machine_code=machine_code):
        licenseKey = None
        print("error: cannot use this license on this machine")
        return licenseUsed
    else:

        licenseKey = result[0]
        print(licenseKey.data_objects)
        # everything went fine if we are here!
        print("The license is valid!")
        return None
        # license_key = result[0]
        # print("Feature 1: " + str(license_key.f1))
        # print("License expires: " + str(license_key.expires))


def licenseDeactivate():
    # loaded from environment only for demo, should be embedded in prod use
    auth = os.environ.get("CL_AUTH_TOKEN", "")
    productId = os.environ.get("CL_PRODUCT_ID", "")

    productKey = os.environ.get("CL_PRODUCT_KEY", "")
    result = Key.deactivate(token=auth,
                            product_id=productId,
                            key=productKey,
                            machine_code=machine_code,
                            floating=True)
    if not result[0]:
        print(result[1])
    else:
        print("license de-activated")


def get_data_objects(objectName: DataObjectNames):
    # loaded from environment only for demo, should be embedded in prod use
    auth = os.environ.get("CL_AUTH_TOKEN", "")
    productId = os.environ.get("CL_PRODUCT_ID", "")

    productKey = os.environ.get("CL_PRODUCT_KEY", "")
    dataObjectsResults = Data.list_key_data_objects(
        token=auth, product_id=productId, key=productKey, name_contains=objectName.value)

    if dataObjectsResults[0] == None:
        print(dataObjectsResults[1])
    return dataObjectsResults[0]["dataObjects"]


def increment_object(objectName: DataObjectNames, increment=1):
    # loaded from environment only for demo, should be embedded in prod use
    auth = os.environ.get("CL_AUTH_TOKEN", "")
    productId = os.environ.get("CL_PRODUCT_ID", "")

    productKey = os.environ.get("CL_PRODUCT_KEY", "")
    dataObjects = get_data_objects(objectName)

    if dataObjects == None:
        exit(1)
    result = Data.increment_int_value_to_key(
        token=auth, product_id=productId, key=productKey, object_id=dataObjects[0]["id"], int_value=increment)
    if result[0] == None:
        print(result[1])
        exit(1)


def decrement_object(objectName: DataObjectNames, decrement=1):
    auth = os.environ.get("CL_AUTH_TOKEN", "")
    productId = os.environ.get("CL_PRODUCT_ID", "")

    productKey = os.environ.get("CL_PRODUCT_KEY", "")
    dataObjects = get_data_objects(objectName)

    if dataObjects == None:
        exit(1)

    result = Data.decrement_int_value_to_key(
        token=auth, product_id=productId, key=productKey, object_id=dataObjects[0]["id"], int_value=decrement)
    if result[0] == None:
        print(result[1])
        exit(1)


def isFeatureEnabled(feature: Features):
    if not licenseKey:
        print("licensing not set in application")
    return hasattr(licenseKey, feature.value) and getattr(licenseKey, feature.value)


def isQuotaAvailable(objectName: DataObjectNames):
    dataObjects = get_data_objects(objectName)
    if dataObjects == None:
        exit(1)
    print(dataObjects)
    print("For `{}` current value is {}".format(
        dataObjects[0]["name"], dataObjects[0]["intValue"]))
    return dataObjects[0]["intValue"] > 0


# =================================================
# Application Startup
# =================================================


def run() -> None:
    licenseFailureResult = licenseCheck()
    if licenseFailureResult:
        print(licenseFailureResult)
        exit(1)
    # start crons in daemon thread
    tl.start(block=False)
    print("starting application server")
    uvicorn.run(
        app,
        port=int(os.getenv("PORT", "8000")),
        host=os.getenv("HOST", "0.0.0.0")
    )


if __name__ == "__main__":
    run()
