import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
from typing import List, Dict, Any
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve MongoDB credentials from environment variables
username = os.getenv("MONGO_USERNAME")
password = os.getenv("MONGO_PASSWORD")
encoded_username = quote_plus(username)
encoded_password = quote_plus(password)

# MongoDB connection
client = MongoClient(f"mongodb+srv://{encoded_username}:{encoded_password}@cluster0.yeodlfo.mongodb.net/?retryWrites=true&w=majority&tls=true")

db = client["roadmap_builder"]
roadmaps_collection = db["roadmaps"]
class_collection = db["class_list"]
booking_collection = db["booking_list"]


app = FastAPI()

# CORS middleware to allow cross-origin requests (for development purposes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify your frontend URL like ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RoadmapRequest(BaseModel):
    userEmail: str
    projectTitle: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class ClassList(BaseModel):
    class_name: str
    class_id: str
    class_description: str
    icon: str
    color: str
    total_slots: int
    bookings: int = 0
    waitlist: int = 0

class Booking(BaseModel):
    class_id: str
    class_name: str
    user_name: str
    user_id: str
    booking_date: str

class CancelBookingRequest(BaseModel):
    class_id: str
    user_id: str


def get_projects_by_email(email: str):
    user_roadmaps = roadmaps_collection.find_one({"email": email}, {"roadmaps.title": 1})
    if user_roadmaps and "roadmaps" in user_roadmaps:
        return [roadmap["title"] for roadmap in user_roadmaps["roadmaps"]]
    else:
        return []

@app.get("/")
def read_root():
    return {"message": "API is running with no issues"}

@app.get("/projects/{email}")
def get_projects(email: str):
    try:
        projects = get_projects_by_email(email)
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {str(e)}")

def save_roadmap(user_email: str, project_title: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]):
    # Find the document for the user
    user_roadmaps = roadmaps_collection.find_one({"email": user_email})
    
    if user_roadmaps:
        # Update existing project or add a new one
        for roadmap in user_roadmaps["roadmaps"]:
            if roadmap["title"] == project_title:
                roadmap["nodes"] = nodes
                roadmap["edges"] = edges
                break
        else:
            user_roadmaps["roadmaps"].append({"title": project_title, "nodes": nodes, "edges": edges})
        roadmaps_collection.update_one({"email": user_email}, {"$set": {"roadmaps": user_roadmaps["roadmaps"]}})
    else:
        # Create a new document if the user does not exist
        new_roadmap = {
            "email": user_email,
            "roadmaps": [{"title": project_title, "nodes": nodes, "edges": edges}]
        }
        roadmaps_collection.insert_one(new_roadmap)

@app.post("/roadmap/save")
def save_roadmap_handler(roadmap: RoadmapRequest):
    try:
        save_roadmap(roadmap.userEmail, roadmap.projectTitle, roadmap.nodes, roadmap.edges)
        return {"message": "Roadmap saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save roadmap: {str(e)}")

@app.get("/roadmap/fetch/{email}/{project_title}")
def fetch_roadmap(email: str, project_title: str):
    try:
        user_roadmaps = roadmaps_collection.find_one({"email": email}, {"roadmaps": 1})
        if user_roadmaps and "roadmaps" in user_roadmaps:
            for roadmap in user_roadmaps["roadmaps"]:
                if roadmap["title"] == project_title:
                    return {"nodes": roadmap["nodes"], "edges": roadmap["edges"]}
        raise HTTPException(status_code=404, detail="Roadmap not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch roadmap: {str(e)}")

@app.post("/create_class/")
async def create_class(class_data: ClassList):
    if class_collection.find_one({"class_id": class_data.class_id}):
        raise HTTPException(status_code=400, detail="Class ID already exists")
    
    class_collection.insert_one(class_data.dict())
    return {"message": "Class created successfully"}

@app.post("/book_slot/")
async def book_slot(booking: Booking):
    class_info = class_collection.find_one({"class_id": booking.class_id})
    
    if not class_info:
        raise HTTPException(status_code=404, detail="Class not found")
    
    booking_data = booking.dict()
    booking_data["class_name"] = class_info["class_name"]

    if class_info['bookings'] >= class_info['total_slots']:
        booking_collection.update_one(
            {"class_id": booking.class_id},
            {"$push": {"waitlist": booking_data}},
            upsert=True
        )
        class_collection.update_one(
            {"class_id": booking.class_id},
            {"$inc": {"waitlist": 1}}
        )
        return {"message": "Added to waitlist"}
    
    booking_collection.update_one(
        {"class_id": booking.class_id},
        {"$push": {"bookings": booking_data}},
        upsert=True
    )
    class_collection.update_one(
        {"class_id": booking.class_id},
        {"$inc": {"bookings": 1}}
    )
    
    return {"message": "Booking confirmed"}

@app.post("/cancel_booking/")
async def cancel_booking(request: CancelBookingRequest):
    class_id = request.class_id
    user_id = request.user_id
    
    booking_info = booking_collection.find_one({"class_id": class_id})
    
    if not booking_info:
        raise HTTPException(status_code=404, detail="Class not found")

    current_bookings_count = len(booking_info.get("bookings", []))

    result = booking_collection.update_one(
        {"class_id": class_id},
        {"$pull": {"bookings": {"user_id": user_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    bookings_removed = current_bookings_count - len(booking_collection.find_one({"class_id": class_id}).get("bookings", []))
    
    update_result = class_collection.update_one(
        {"class_id": class_id},
        {"$inc": {"bookings": -bookings_removed}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update class bookings")

    if booking_info.get("waitlist") and len(booking_info["waitlist"]) > 0:
        waitlist_entry = booking_info["waitlist"][0]
        booking_collection.update_one(
            {"class_id": class_id},
            {
                "$push": {"bookings": waitlist_entry},
                "$pull": {"waitlist": waitlist_entry}
            }
        )
        class_collection.update_one(
            {"class_id": class_id},
            {"$inc": {"waitlist": -1, "bookings": 1}}
        )
        return {"message": "Booking canceled, waitlist updated"}
    
    return {"message": "Booking canceled successfully"}

@app.get("/class_list/")
async def fetch_class_list():
    try:
        classes = list(class_collection.find({}))
        for cls in classes:
            cls["_id"] = str(cls["_id"])
        return {"classes": classes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user_bookings/{user_id}")
async def fetch_user_bookings(user_id: str):
    bookings = booking_collection.find({"bookings.user_id": user_id})
    results = []
    
    for class_info in bookings:
        for booking in class_info.get("bookings", []):
            if booking["user_id"] == user_id:
                results.append({
                    "class_id": class_info["class_id"],
                    "class_name": booking["class_name"],
                    "booking_date": booking["booking_date"]
                })
    
    if not results:
        raise HTTPException(status_code=404, detail="No bookings found for this user")
    
    return {"user_bookings": results}
