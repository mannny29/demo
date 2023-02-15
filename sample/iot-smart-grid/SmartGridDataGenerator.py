import hydra
from hydra.core.config_store import ConfigStore
import asyncio
import uuid
import random
import json
from datetime import *
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config
from marshmallow import fields
from azure.storage.filedatalake import DataLakeServiceClient, DataLakeFileClient, FileSystemClient
from config import *

# ConfigStore for Hydra
cs = ConfigStore.instance()
cs.store(name="iot_smart_grid_config", node=IotSmartGridConfig)

ZIP_CODE_RANGE = range(98001, 98101)
METER_ID_RANGE = range(1,5)
MEASUREMENT_MIN = 8.0
MEASUREMENT_MAX = 20.0

@dataclass_json
@dataclass
class SmartGridData: 
    meterId: str
    measurementInKWh: float
    zipCode: str
    measurementDate: str = field(
        default_factory=datetime.now,
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        ))

# Write the Smart Grid data into the Data Lake
async def writeDataToADLS(smartDataList, fsClient, dataLakeFolder) -> None:
    filename = f'{dataLakeFolder}/smartGridData-{str(uuid.uuid4())}.json'

    # Convert the smartDataList into a JSON format.
    jsonData = "\n".join([data.to_json() for data in smartDataList])
    jsonDataLen = len(jsonData)

    print(f'Writing file - {filename}')

    try:
        fileClient = fsClient.create_file(file=filename)
        fileClient.append_data(jsonData, offset=0, length=jsonDataLen)
        fileClient.flush_data(jsonDataLen)

        print(f'Success - Writing file - {filename}')
    except Exception as ex:
        print(f'Failed - Writing file - {filename} - {ex}')

# Create the Smart Grid data
async def createSmartGridData(zipCodeList, meterIdRange, numOfMeterReading, sleepTimer) -> list:
    data = []

    await asyncio.sleep(sleepTimer)
    
    # Create smart grid data. For each zip code, we want an average of numOfMeterReading.
    for x in range(0, len(zipCodeList)*numOfMeterReading):
        selectMeterId = random.choice(meterIdRange)
        zipCode = random.choice(zipCodeList)

        meterId = f"{zipCode}-{selectMeterId}"
        measurementInKwh = random.uniform(MEASUREMENT_MIN, MEASUREMENT_MAX)

        data.append(SmartGridData(meterId=meterId, measurementInKWh=measurementInKwh, zipCode=zipCode))
    
    return data

# Create the data, convert it into JSON and write to Data Lake (parquet file format).
async def generateSmartGridData(zipCodeList, meterIdRange, numOfMeterReading, sleepTimer, fsClient, dataLakeFolder) -> None:
    result = await createSmartGridData(zipCodeList, meterIdRange, numOfMeterReading, sleepTimer)
    print('Result generated...')
    await writeDataToADLS(result, fsClient, dataLakeFolder)

# Create the data, convert it into JSON and write to Data Lake (parquet file format).
async def asyncSmartGridData(zipCodeBatches, meterIdList, numOfMeterReading, maxSleepTimer, fsClient, dataLakeFolder) -> None:
    # ASync to Generate and process the data.
    await asyncio.gather(*[generateSmartGridData(b, meterIdList, numOfMeterReading, random.randint(1,maxSleepTimer), fsClient, dataLakeFolder) for b in zipCodeBatches])


@hydra.main(config_path="config", config_name="config")
def main(cfg:IotSmartGridConfig) -> None: 
    zipCodeList = list(ZIP_CODE_RANGE)
    meterIdList = list(METER_ID_RANGE)

    # divide the zip code into batches
    zipCodeBatches = [zipCodeList[x:x+cfg.params.num_of_batches] for x in range(0, len(zipCodeList), cfg.params.num_of_batches)]

    # Create a data lake connection
    if len(zipCodeBatches) > 0:
        connectionString = f'DefaultEndpointsProtocol=https;AccountName={cfg.env.data_lake_name};AccountKey={cfg.env.data_lake_access_key};EndpointSuffix=core.windows.net'
        adlsClient = DataLakeServiceClient.from_connection_string(conn_str=connectionString)
        fsClient = adlsClient.get_file_system_client(file_system=cfg.env.data_lake_container)

        print(f'Connecting to: {cfg.env.data_lake_name} - Container: {cfg.env.data_lake_container} - Data Lake folder: {cfg.env.data_lake_folder}')

        # Create and process the Smart Grid data - Async
        asyncio.run(asyncSmartGridData(zipCodeBatches, meterIdList, cfg.params.num_of_meter_reading, cfg.params.max_sleep_timer, fsClient, cfg.env.data_lake_folder))

if __name__ == "__main__":
    main()
    