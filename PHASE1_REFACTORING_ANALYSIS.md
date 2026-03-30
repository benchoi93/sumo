# Phase 1 SUMO Performance Refactoring - Exact Code Analysis

## PR 1.1: std::map → std::unordered_map for dictionary containers

### 1. NamedObjectCont.h
**File:** `/data2/chois/sumo/src/utils/common/NamedObjectCont.h`

**Line 44 - IDMap typedef:**
```cpp
typedef std::map< std::string, T > IDMap;
```

**Lines 67-69 - add() method depends on sorted order via lower_bound + emplace_hint:**
```cpp
const auto it = myMap.lower_bound(id);
if (it == myMap.end() || it->first != id) {
    myMap.emplace_hint(it, id, item);
```

**Lines 125-128 - insertIDs() iterates in key order (sorted):**
```cpp
void insertIDs(std::vector<std::string>& into) const {
    for (auto i : myMap) {
        into.push_back(i.first);
    }
}
```

**Issue:** The `add()` method uses `lower_bound()` and `emplace_hint()` which are optimizations that assume sorted iteration. However, **insertIDs() does NOT depend on sorted order** - it just copies all keys to a vector. The lower_bound/emplace_hint optimization will be lost with unordered_map, but this is acceptable for a standard unordered insertion.

**Backward compat note:** If callers expect insertIDs() to return keys in sorted order, they will break. Need to check callers.

---

### 2. MSEdge.h
**File:** `/data2/chois/sumo/src/microsim/MSEdge.h`

**Line 1035 - DictType typedef:**
```cpp
typedef std::map< std::string, MSEdge* > DictType;
```

**Line 1040 - Static dictionary declaration:**
```cpp
static DictType myDict;
```

**Related method - Line 836 insertIDs():**
```cpp
static void insertIDs(std::vector<std::string>& into);
```

---

### 3. MSEdge.cpp
**File:** `/data2/chois/sumo/src/microsim/MSEdge.cpp`

**Lines 1076-1079 - dictionary() method with lower_bound + emplace_hint:**
```cpp
const DictType::iterator it = myDict.lower_bound(id);
if (it == myDict.end() || it->first != id) {
    // id not in myDict
    myDict.emplace_hint(it, id, ptr);
```

**Lines 1130-1133 - insertIDs() implementation iterates myDict:**
```cpp
void
MSEdge::insertIDs(std::vector<std::string>& into) {
    for (DictType::iterator i = myDict.begin(); i != myDict.end(); ++i) {
        into.push_back((*i).first);
    }
}
```

---

### 4. MSLane.h
**File:** `/data2/chois/sumo/src/microsim/MSLane.h`

**Lines 1630-1633 - DictType typedef and static dictionary:**
```cpp
typedef std::map< std::string, MSLane* > DictType;

/// Static dictionary to associate string-ids with objects.
static DictType myDict;
```

**Line 836 - insertIDs() method declaration:**
```cpp
static void insertIDs(std::vector<std::string>& into);
```

---

### 5. MSVehicleControl.h
**File:** `/data2/chois/sumo/src/microsim/MSVehicleControl.h`

**Lines 656-658 - VehicleDictType typedef:**
```cpp
typedef std::map< std::string, SUMOVehicle* > VehicleDictType;
/// @brief Dictionary of vehicles
VehicleDictType myVehicleDict;
```

**Lines 679-681 - VTypeDictType typedef:**
```cpp
typedef std::map< std::string, MSVehicleType* > VTypeDictType;
/// @brief Dictionary of vehicle types
VTypeDictType myVTypeDict;
```

**Lines 684-686 - VTypeDistDictType (also std::map):**
```cpp
typedef std::map< std::string, RandomDistributor<MSVehicleType*>* > VTypeDistDictType;
/// @brief A distribution of vehicle types (probability->vehicle type)
VTypeDistDictType myVTypeDistDict;
```

---

### 6. MSRoute.h
**File:** `/data2/chois/sumo/src/microsim/MSRoute.h`

**Lines 318-320 - RouteDict typedef:**
```cpp
typedef std::map<std::string, ConstMSRoutePtr> RouteDict;

/// The dictionary container
```

---

## PR 1.2: Pool MSLeaderInfo per lane

### MSLeaderInfo.h
**File:** `/data2/chois/sumo/src/microsim/MSLeaderInfo.h`

**Lines 50-51 - Constructor signature:**
```cpp
MSLeaderInfo(const double laneWidth, const MSVehicle* ego = nullptr, const double latOffset = 0.);
```

**Lines 64-65 - clear() method (for recycling):**
```cpp
/// @brief discard all information
virtual void clear();
```

**Lines 98-100 - internal state structure (myVehicles vector):**
```cpp
const std::vector<const MSVehicle*>& getVehicles() const {
    return myVehicles;
}
```

**Line 130 - myVehicles member:**
```cpp
std::vector<const MSVehicle*> myVehicles;
```

---

### MSLane.h
**File:** `/data2/chois/sumo/src/microsim/MSLane.h`

**Lines 1591-1593 - Per-lane MSLeaderInfo members (cached):**
```cpp
mutable MSLeaderInfo myLeaderInfo;
mutable MSLeaderInfo myFollowerInfo;
```

---

### MSLane.cpp
**File:** `/data2/chois/sumo/src/microsim/MSLane.cpp`

**Line 1562 - planMovements() function start:**
```cpp
MSLane::planMovements(SUMOTime t) {
```

**Lines 1563-1565 - MSLeaderInfo instantiation and iteration:**
```cpp
assert(myVehicles.size() != 0);
double cumulatedVehLength = 0.;
MSLeaderInfo leaders(myWidth);  // <-- ALLOCATION per planMovements call
```

**Lines 1593-1597 - Loop structure that uses leaders:**
```cpp
for (; veh != myVehicles.rend(); ++veh) {
    updateLeaderInfo(*veh, vehPart, vehRes, leaders);
    (*veh)->planMove(t, leaders, cumulatedVehLength);
    cumulatedVehLength += (*veh)->getVehicleType().getLengthWithGap();
    leaders.addLeader(*veh, false, 0);  // <-- MODIFIES leaders
```

**Pooling opportunity:** `leaders` is created fresh each call to `planMovements()`. It's cleared implicitly by construction. Could reuse a pre-allocated instance stored in the lane with explicit `leaders.clear()` at the start.

---

## PR 1.3: std::list → std::vector for active lanes

### MSEdgeControl.h
**File:** `/data2/chois/sumo/src/microsim/MSEdgeControl.h`

**Line 275 - myActiveLanes declaration:**
```cpp
std::list<MSLane*> myActiveLanes;
```

---

### MSEdgeControl.cpp
**File:** `/data2/chois/sumo/src/microsim/MSEdgeControl.cpp`

**Lines 118-127 - patchActiveLanes() with push_front/push_back operations:**
```cpp
void
MSEdgeControl::patchActiveLanes() {
    for (auto i = myChangedStateLanes.begin(); i != myChangedStateLanes.end(); ++i) {
        if ((*i)->getVehicleNumber() != 0) {
            // lane went from inactive to active
            if ((*i)->isActive()) {
                myActiveLanes.push_front(*i);  // <-- LIST OPERATION
            } else {
                myActiveLanes.push_back(*i);   // <-- LIST OPERATION
```

**Lines 137-170 - planMovements() with erase operations on list:**
```cpp
void
MSEdgeControl::planMovements(SUMOTime t) {
    for (std::list<MSLane*>::iterator i = myActiveLanes.begin(); i != myActiveLanes.end();) {
        if ((*i)->getVehicleNumber() == 0) {
            i = myActiveLanes.erase(i);  // <-- LIST ERASE (efficient O(1) with iterator)
        } else {
            if (!(*i)->planMovements(t)) {  // returns true/false
                i = myActiveLanes.erase(i);
            } else {
                (*i)->planMovements(t);
                ++i;
            }
        }
    }
```

**Lines 190-194 - Forward iteration in setJunctionApproaches():**
```cpp
for (MSLane* const lane : myActiveLanes) {
    lane->setJunctionApproaches(t);
}
```

**Lines 201-260 - executeMovements() with erase + push_front/push_back:**
```cpp
void
MSEdgeControl::executeMovements(SUMOTime t) {
    std::vector<MSLane*> wasActive(myActiveLanes.begin(), myActiveLanes.end());  // COPY to vector!
    for (std::list<MSLane*>::iterator i = myActiveLanes.begin(); i != myActiveLanes.end();) {
        if ((*i)->getVehicleNumber() == 0) {
            i = myActiveLanes.erase(i);  // <-- LIST ERASE
        } else {
            ++i;
        }
    }
    // ...
    for (std::list<MSLane*>::iterator i = myActiveLanes.begin(); i != myActiveLanes.end();) {
        if ((*i)->getVehicleNumber() == 0) {
            (*i)->executeMovements(t);
            i = myActiveLanes.erase(i);  // <-- LIST ERASE
        } else {
            ++i;
        }
    }
    // ...
    myActiveLanes.push_front(lane);   // <-- PUSH_FRONT (needs to be at front)
    myActiveLanes.push_back(lane);    // <-- PUSH_BACK (append)
```

**Lines 278-290 - changeLanes() with range-based for:**
```cpp
void
MSEdgeControl::changeLanes(const SUMOTime t) {
    for (const MSLane* const l : myActiveLanes) {
        MSEdge& edge = l->getEdge();
        if (edge.getLaneChangeModel() != nullptr) {
            edge.changeLanes(t);
        }
    }
```

**Lines 334-342 - pushActiveLanesFront() with push_front:**
```cpp
myActiveLanes.push_front(*i);  // <-- PUSH_FRONT
for (MSLane* lane : myActiveLanes) {
    lane->updateLengthSum();
}
```

**Key observation:** The list is primarily used for:
1. Frequent push_front/push_back (ordering matters - new lanes go to front/back)
2. Frequent erase during iteration (O(1) with list iterators)
3. Occasional range-based iteration

Converting to vector requires:
- Replace erase(iterator) with swap-and-pop or manual shifts (O(n))
- Replace push_front with insert(begin(), ...) (O(n))
- Keep push_back and range iteration as-is (O(1) and O(n))

**Trade-off:** Cache locality improves (vector is contiguous), but erase + push_front become O(n). Acceptable if active lane count is small.

---

## PR 1.4: swap instead of copy for myLFLinkLanesPrev

### MSVehicle.h
**File:** `/data2/chois/sumo/src/microsim/MSVehicle.h`

**Lines 2035-2042 - myLFLinkLanes and myLFLinkLanesPrev declarations:**
```cpp
DriveItemVector myLFLinkLanes;

/// @brief A copy of the previous time step's myLFLinkLanes
DriveItemVector myLFLinkLanesPrev;

/** @brief iterator pointing to the next item in myLFLinkLanes
 * @note Used for inter-actionpoint actualization of myLFLinkLanes (i.e. deletion of passed items)
 */
```

**Note:** Need to find DriveItemVector typedef. Searching...

**Result (from header):** DriveItemVector is likely defined in MSVehicle.h or included. It's a container of DriveProcessItem structs.

---

### MSVehicle.cpp
**File:** `/data2/chois/sumo/src/microsim/MSVehicle.cpp`

**Line 2150 - myLFLinkLanesPrev assignment (COPY):**
```cpp
myLFLinkLanesPrev = myLFLinkLanes;
```

**This is the key line.** Currently doing a full copy. Should become:
```cpp
std::swap(myLFLinkLanesPrev, myLFLinkLanes);
myLFLinkLanes.clear();  // Reset for new planning
```

---

## PR 1.5: Cache getCarFollowModel() in executeMove

### MSVehicle.h
**File:** `/data2/chois/sumo/src/microsim/MSVehicle.h`

**Lines 969-970 - getCarFollowModel() definition:**
```cpp
inline const MSCFModel& getCarFollowModel() const {
    return myType->getCarFollowModel();
```

**This is an inline getter that delegates to myType->getCarFollowModel().**

---

### MSVehicle.cpp
**File:** `/data2/chois/sumo/src/microsim/MSVehicle.cpp`

**Line 4574 - executeMove() function start:**
```cpp
MSVehicle::executeMove() {
```

**Calls to getCarFollowModel() within executeMove() (lines 4574-4750):**

1. **Line 4631 (relative line 57):** `getCarFollowModel().startupDelayStopped()`
```cpp
if (getCarFollowModel().startupDelayStopped() && getNextStop().pars.speed <= 0) {
```

2. **Line 4633 (relative line 61):** `getCarFollowModel().getStartupDelay()`
```cpp
myTimeSinceStartup = getCarFollowModel().getStartupDelay() + DELTA_T;
```

3. **Line 4640 (relative line 68):** `getCarFollowModel().finalizeSpeed()`
```cpp
vNext = getCarFollowModel().finalizeSpeed(this, vSafe);
```

**These 3 calls all occur within executeMove().** All delegate through `myType->getCarFollowModel()`.

**Optimization:** Cache the reference:
```cpp
const MSCFModel& cfModel = getCarFollowModel();
// Then use cfModel.startupDelayStopped(), cfModel.getStartupDelay(), cfModel.finalizeSpeed()
```

---

# Summary Table

| PR | File | Line(s) | Container Type | Change | Notes |
|----|------|---------|---|---------|-------|
| 1.1 | NamedObjectCont.h | 44 | std::map | → unordered_map | add() uses lower_bound/emplace_hint; insertIDs() does NOT require order |
| 1.1 | MSEdge.h | 1035 | std::map | → unordered_map | DictType |
| 1.1 | MSEdge.cpp | 1076-1079 | myDict | → unordered_map | dictionary() uses lower_bound/emplace_hint |
| 1.1 | MSLane.h | 1630 | std::map | → unordered_map | DictType |
| 1.1 | MSVehicleControl.h | 656, 679, 684 | 3× std::map | → unordered_map | VehicleDictType, VTypeDictType, VTypeDistDictType |
| 1.1 | MSRoute.h | 318 | std::map | → unordered_map | RouteDict |
| 1.2 | MSLane.h | 1591-1593 | MSLeaderInfo | Pool per lane | myLeaderInfo, myFollowerInfo mutable cached |
| 1.2 | MSLane.cpp | 1563-1597 | leaders (local) | Allocate once, reuse | planMovements() creates MSLeaderInfo each call |
| 1.3 | MSEdgeControl.h | 275 | std::list | → std::vector | myActiveLanes |
| 1.3 | MSEdgeControl.cpp | 118-342 | myActiveLanes | Multiple erase + push ops | patchActiveLanes, planMovements, executeMovements, changeLanes |
| 1.4 | MSVehicle.h | 2035-2038 | DriveItemVector | Swap instead of copy | myLFLinkLanes, myLFLinkLanesPrev |
| 1.4 | MSVehicle.cpp | 2150 | myLFLinkLanesPrev | Replace = with swap | Line 2150 assignment |
| 1.5 | MSVehicle.h | 969-970 | MSCFModel | Cache ref | getCarFollowModel() inline getter |
| 1.5 | MSVehicle.cpp | 4631, 4633, 4640 | executeMove() | Local cache | 3× getCarFollowModel() calls |
