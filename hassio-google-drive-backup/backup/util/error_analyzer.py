import asyncio
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pathlib import Path

KNWON_ERRORS = ['existing_backup_folder', 'google_dns', 'cancelled', 'google_timeout', 'low_space', 'multiple_deletes']


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
            await stats(db, reports)
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


async def stats(db, reports):
    print("Inspecting the last 24 hours of records...")
    cursor = None
    batch_size = 50
    summary = {}
    resolved = {}
    total = 0
    while True:
        count = 0
        if cursor is None:
            stream = reports.limit(batch_size).stream()
        else:
            stream = reports.limit(batch_size).start_after(cursor).stream()
        for report in stream:
            cursor = report
            data = report.to_dict()
            count += 1
            total += 1
            if 'report' not in data:
                continue
            if 'error' not in data['report']:
                resolved[data['client']] = data['report']['duration']
                continue
            if data['report']['error'] in summary:
                summary[data['report']['error']].append(data)
            else:
                summary[data['report']['error']] = [data]
        print("Processed " + str(count) + " records")
        if count == 0:
            break
    for error in summary.keys():
        print("")
        distinct = set()
        unresolved = {}
        versions = set()
        for report in summary[error]:
            distinct.add(report['client'])
            if report['client'] not in resolved:
                unresolved[report['client']] = report
            versions.add(report['version'])
        print("Unresolved: " + str(len(unresolved)))
        print("Count: " + str(len(summary[error])))
        print("Distinct: " + str(len(distinct)))
        print("Versions: " + str(versions))
        print("Error: " + error)
        if len(unresolved) > 0:
            print("Unresolved: ")
            for unres in unresolved.values():
                print("  " + unres['report']['arch'] + " " + unres['client'])
    print("Total records: " + str(total))


if __name__ == '__main__':
    asyncio.run(main())
