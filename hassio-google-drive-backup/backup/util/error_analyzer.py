import asyncio
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pathlib import Path


async def main():
    cred = credentials.Certificate(str(Path.home().joinpath("Documents/secrets/server-firestore-creds.json")))
    firebase_admin.initialize_app(cred)

    db = firestore.client()
    reports = db.collection(u'error_reports')

    while(True):
        command = input()
        if command == "clear all":
            print("Deleteing records...")
            batch = db.batch()
            batch_size = 0
            for item in reports.stream():
                batch.delete(reports.document(item.id))
                batch_size += 1
            batch.commit()
            print("Done")
        if command == "":
            # Do regular analysis
            print("Inspecting the last 24 hours of records...")
            for item in reports.stream():
                pass
        if command.startswith("get "):
            query = reports.where("report.client", "==", command[4:])
            for report in query.get():
                print(report.to_dict())
            print("done")
        elif command == "exit" or command == "quit" or command == "q":
            return

    # stream = reports.stream()
    for report in query.get():
        print(report.to_dict())

if __name__ == '__main__':
    asyncio.run(main())
