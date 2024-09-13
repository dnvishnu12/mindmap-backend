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
# username = os.getenv("MONGO_USERNAME")
# password = os.getenv("MONGO_PASSWORD")
# encoded_username = quote_plus(username)
# encoded_password = quote_plus(password)

client = MongoClient(f"mongodb+srv://dnvishnu:Fu99NSbZqN8wN4ks@cluster0.yeodlfo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

db = client["roadmap_builder"]
roadmaps_collection = db["roadmaps"]


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
