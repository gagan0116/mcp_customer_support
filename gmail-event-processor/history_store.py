from google.cloud import firestore

db = firestore.Client()
DOC = db.collection("gmail").document("history")

def load_history_id():
    doc = DOC.get()
    return int(doc.to_dict()["history_id"]) if doc.exists else None

def save_history_id(hid):
    DOC.set({"history_id": hid})
