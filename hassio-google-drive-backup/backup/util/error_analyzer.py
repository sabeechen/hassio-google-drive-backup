import asyncio
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime
from pathlib import Path

async def main():
    cred = credentials.Certificate(str(Path.home().joinpath("Documents/secrets/server-firestore-creds.json")))
    firebase_admin.initialize_app(cred)

    db = firestore.client()
    reports = db.collection(u'error_reports')
    query = reports.where("report.client", "==", "s0703a7dd-a1ff-4210-9a0b-932e79d2644f")
    #stream = reports.stream()
    for report in query.get():
        print(report.to_dict())

if __name__ == '__main__':
    asyncio.run(main())
