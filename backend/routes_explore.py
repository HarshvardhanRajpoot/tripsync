"""
Explore endpoints. Hook into main.py with two lines:

    import routes_explore
    app.include_router(routes_explore.router)
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import auth
import explore_service
import models

router = APIRouter(prefix="/api/explore", tags=["explore"])


@router.get("/states")
def list_states(current_user: models.User = Depends(auth.get_current_user)):
    return explore_service.get_states()


@router.get("/districts")
def list_districts(state: str = Query(...), current_user: models.User = Depends(auth.get_current_user)):
    districts = explore_service.get_districts(state)
    if districts is None:
        raise HTTPException(status_code=404, detail="Unknown state")
    return districts


@router.get("/places")
def top_places(state: str = Query(...), district: str = Query(...),
               current_user: models.User = Depends(auth.get_current_user)):
    districts = explore_service.get_districts(state)
    if districts is None or district not in districts:
        raise HTTPException(status_code=404, detail="Unknown state or district")
    try:
        found = explore_service.top_places(state, district)
    except explore_service.ExploreError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "state": state,
        "district": district,
        "maps_search_url": explore_service.maps_search_url(district, state),
        "source": found["source"],
        "note": found["note"],
        "places": found["places"],
    }
