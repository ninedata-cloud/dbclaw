import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=192.168.2.62,1412;"
    "DATABASE=master;"
    "UID=sa;"
    "PWD=NineData99;"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
)

cursor = conn.cursor()
cursor.execute("SELECT GETDATE()")
print(cursor.fetchone())