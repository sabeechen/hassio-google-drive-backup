import argparse
from google.cloud import firestore
from datetime import datetime, timedelta
DELETE_BATCH_SIZE = 200
STORE_NAME = "error_reports"

# Before running, set up firestore credentials with these commands:
#  pip install --upgrade google-cloud-firestore
#  gcloud auth login
#  gcloud config set project hassio-drive-backup
#  gcloud iam service-accounts keys create keyfile.json --iam-account firestore-testing@hassio-drive-backup.iam.gserviceaccount.com
#  export GOOGLE_APPLICATION_CREDENTIALS=keyfile.json

def delete_old_data():
    # Initialize Firestore
    db = firestore.Client()
    collection_ref = db.collection(STORE_NAME)

    # Define the datetime for one week ago
    week_ago = datetime.now() - timedelta(days=7)

    # Query to find all documents older than a week
    total_deleted = 0
    while True:
        to_delete = 0
        batch = db.batch()
        docs = collection_ref.where('server_time', '<', week_ago).stream()
        for doc in docs:
            to_delete += 1
            batch.delete(doc.reference)
            if to_delete >= DELETE_BATCH_SIZE:
                break
        if to_delete > 0:
            batch.commit()
            total_deleted += to_delete
            print(f"Deleted {to_delete} documents ({total_deleted} total)")
        else:
            break
    print(f"Success: All documents older than a week deleted ({total_deleted} total)")


def main():
    # Create command line argument parser
    parser = argparse.ArgumentParser()

    # Add purge argument
    parser.add_argument("--purge", help="Delete all documents older than a week.", action="store_true")

    # Add any other argument you want in future. For example:
    # parser.add_argument("--future_arg", help="Perform some future operation.")

    args = parser.parse_args()

    # Respond to arguments
    if args.purge:
        confirm = input('Are you sure you want to delete all documents older than a week? (y/n): ')
        if confirm.lower() == 'y':
            delete_old_data()
        else:
            print("Abort: No documents were deleted.")

if __name__ == "__main__":
    main()