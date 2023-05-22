import io
import oci
import os
import csv
import random
import oracledb
import logging
from zipfile import ZipFile
from timeit import default_timer as timer
import string


def get_dbwallet_from_autonomousdb(dbwallet_dir, signer):
    dbwalletzip_location = "/tmp/dbwallet.zip"
    adb_ocid = os.getenv("ADB_OCID")     

    atp_client = oci.database.DatabaseClient(config={}, signer=signer)
    atp_wallet_pwd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=15)) # random string
    # the wallet password is only used for creation of the Java jks files, which aren't used by cx_Oracle so the value is not important
    atp_wallet_details = oci.database.models.GenerateAutonomousDatabaseWalletDetails(password=atp_wallet_pwd)
    print(atp_wallet_details, flush=True)
    obj = atp_client.generate_autonomous_database_wallet(adb_ocid, atp_wallet_details)
    with open(dbwalletzip_location, 'w+b') as f:
        for chunk in obj.data.raw.stream(1024 * 1024, decode_content=False):
            f.write(chunk)
    with ZipFile(dbwalletzip_location, 'r') as zipObj:
            zipObj.extractall(dbwallet_dir)
    logging.getLogger().info("wallet generated.......")     
    return atp_wallet_pwd   


def get_connection(dbwallet_dir, signer):          
    dbuser = os.getenv("DBUSER")
    dbpwd = os.getenv("DBPWD")
    dbsvc = os.getenv("DBSVC")
    wallet_password = get_dbwallet_from_autonomousdb(dbwallet_dir, signer)

    # Update SQLNET.ORA
    with open(dbwallet_dir + '/sqlnet.ora') as orig_sqlnetora:
        newText=orig_sqlnetora.read().replace('DIRECTORY=\"?/network/admin\"', 
        'DIRECTORY=\"{}\"'.format(dbwallet_dir))
    with open(dbwallet_dir + '/sqlnet.ora', "w") as new_sqlnetora:
        new_sqlnetora.write(newText)

    logging.getLogger().info("sqlnet.ora: "+ newText )
    # Create the DB Session Pool            
    logging.getLogger().info("dbwallet_dir: "+ dbwallet_dir )
    dbconnection = oracledb.connect(user=dbuser, password=dbpwd, dsn=dbsvc,
                              config_dir=dbwallet_dir, wallet_location=dbwallet_dir, 
                              wallet_password=wallet_password)    

    logging.getLogger().info("Connection "+ dbsvc +" created ")
    return dbconnection


def create_table(dbconnection):    
    try:
        with dbconnection.cursor() as dbcursor:
            start_query = timer()
            out_val = dbcursor.var(str)
            dbcursor.execute("""begin
                            execute immediate 'DROP TABLE DATOS_CLIENTE';
                            exception when others then
                            if sqlcode <> -942 then
                                raise;
                            end if;
                        end;""")
            dbcursor.execute("""CREATE TABLE DATOS_CLIENTE (
                        DOC number(9) not null,
                        NOMBRE varchar2(2000),
                        APELLIDO varchar2(2000),
                        EDAD number(15),
                        GENERO varchar2(2000),
                        ESTADO_CIVIL varchar2(2000),
                        OCUPACION varchar2(2000),
                        DIRECCION varchar2(2000),
                        LICENCIA_CONDUCCION varchar2(2000),
                        F_EMISION varchar2(2000),
                        CATEGORIA varchar2(2000),
                        ANTECEDENTES varchar2(2000),
                        ID_ANTECEDENTES varchar2(2000),
                        MULTAS varchar2(2000),
                        ID_MULTAS varchar2(2000),
                        SALDO varchar2(2000),
                        RECLAMACIONES varchar2(2000),
                        constraint TestTempTable_pk primary key (DOC))""")

            end_query = timer()  
            logging.getLogger().info("Outcome creation table " + out_val.getvalue())
            logging.getLogger().info("INFO: Outcome creation table".format(end_query - start_query))
            
    except Exception as e:
        logging.getLogger().info("Failed:" + str(e))                    

def load_data(input_csv_text, dbconnection):
    try:
        reader = csv.DictReader(input_csv_text.split('\n'), delimiter=',')
        info_db = [(line['ID'], line['DOC'], line['APELLIDO'], line['EDAD'], line['GENERO'], line['ESTADO_CIVIL'], line['OCUPACION'], line['DIRECCION'], line['LICENCIA_CONDUCCION'], line['F_EMISION'], line['CATEGORIA'], line['ANTECEDENTES'], line['ID_ANTECEDENTES'], line['MULTAS'], line['ID_MULTAS'], line['SALDO'], line['RECLAMACIONES']) for line in reader]

        with dbconnection.cursor() as dbcursor:        
            logging.getLogger().info("Inserting .....")

            dbcursor.executemany("INSERT INTO DATOS_CLIENTE VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13, :14, :15, :16, :17)", info_db, batcherrors=True)
            dbconnection.commit()
            for error in dbcursor.getbatcherrors():                    
                logging.getLogger().error(error.message)
        
    except Exception as e:
        logging.getLogger().error("Failed:" + str(e))
