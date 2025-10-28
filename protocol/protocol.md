## Transport Protocols: 
TCP, one connection per client to the server. TCP was chosed because we need reliable, in order delivery of messages: authentication and ride requests and chat messages depend on that criteria. Even in P2P chat, TCP is the chosen protocol.

## Message: 
Each message (except error messages) between the client and the server must be as follows:

```json
{
    {
        "type": "<MessageType>", //types defined below
        "id": "<UUIDv4>",
        //this is needed for when we have multiple clients sending messages to the server at the same time. the server needs to reply with the correct answer to the correct client.
        //also we chose UUID version 4 because we want the client to randomly generate an id and send it when initiating a convo. If something fails, we will include that id in the error message sent back. the same id value from the client will be echoed back by the server.
        "auth": { "token": "<JWT token>"} //required for all flows post login
        "payload":
        {
            { } // optional, in case message needs details }
        }
    }
}

```
## All Message Types:
- AUTH (REGISTER and LOGIN) 
- PROFILE (SET and GET)
- SCHEDULE (INSERT)
- RIDE (REQUEST, DECISION, server BROADCAST and MATCH events)
- CHAT (PEERINFO)
- ERROR

## Future features that can be added:
- AUTH: REFRESH. once a session times out for a user, we can REFRESH authentication instead of making the user log in again. adding a timer on the session will be needed too.
- PROFILE: UPDATE. the user can update his/her profile
- SCHEDULE: UPDATE AND DELETE. user can update his/her schedule or delete it

## Message Mapping:
All messages have REQ and RES unless stated otherwise, as EVT (event)
### 1. AUTH:
- AUTH.REGISTER
- AUTH.LOGIN 
- AUTH.LOGOUT

### 2. Profile:
- PROFILE.SET
- PROFILE.GET

### 3. Schedule:
- SCHEDULE.SET
- SCHEDULE.GET
- SCHEDULE.SEARCH

### 4. Ride:
- RIDE.REQUEST
- RIDE.BROADCAST -> this will follow an EVT structure not REQ/RES structure
- RIDE.ACCEPT
- RIDE.DECLINE
- RIDE.MATCH -> this will follow an EVT structure not REQ/RES structure
- RIDE.CANCEL

### 5. Ratings:
- RATING.GET
- RATING.SET

### 6. Chat:
- CHAT.SEND
- CHAT.RCV
- CHAT.CLOSE

### 6. Error Codes
### A. Transport Error Messages:
- BAD_REQUEST: "missing required fields"
in envelope, there is a missing required field, 
- UNAUTHORIZED: "no auth token found"
message comes from an unauthorized source (auth token is misisng)
- FORBIDDEN: "action not allowed"
for example, if a someone who has a driver state is requesting a ride. 
- NOT_FOUND: "requested entity is missing"
for example, looking for a schedule that doesnt exist in db
- CONFLICT: "conflicting states"
for example, a driver accepts a ride request after that ride request has already been fulfilled.
- SERVER_BUSY: "server is temporary overloaded"
- RATE_LIMITED: "allowed request rate exceeded"
- INTERNAL_ERROR: "something went wrong"
- TIMEOUT: "waiting for server/peer timed out"
- PING: checking if server/client connection is still valid
- PONG: confirming that server/client connection is valid

### B. AUTH
- AUTH_INVALID_CREDENTIALS
- AUTH_TOKEN_INVALID: auth token is broken/fake
- AUTH_USERNAME_TAKEN
- AUTH_EMAIL_TAKEN

### C. Profile
- PROFILE_INVALID_FIELD: field in message does not have expected value
- PROFILE_AREA_REQUIRED

### D. Ride
- RIDE_OUTSIDE_SCOPE: requested area is not supported
- RIDE_TIME_IN_PAST: pick up time is before current time
- RIDE_NO_AVAILABLE_DRIVERS: no one is available for this request
- RIDE_ALREADY_ACCEPTED: duplicate acceptances
- RIDE_REQUEST_NOT_FOUND: request reply is referencing a missing/expried request
- RIDE_REQUEST_EXPIRED: driver accepts request too late/match was already made

### E. Ratings:
- RATING_INVALID_SCORE: out of range (1-5)
- RATING_DUPLICATE: rating already sent
- RATING_RIDE_NOT_COMPLETED: rating a ride that is not completed yet

### F. Chat
- CHAT_NOT_ALLOWED: peers not matched so chat is not allowed
- CHAT_PEER_UNREACHABLE: TCP connection fails
- CHAT_MESSAGE_TOO_LARGE: message (frame) limit exceeded
- CHAT_SESSION_CLOSED: peer closed chat, no new messages accepted


## Error:
All error messages from server to client shouldl look like:
```json
{
    "type": "ERROR",
    "id": "<request UUID>",
    "payload": 
    {
        "code": "<ERROR_NAME>",
        "message": "<error definition>",
        "details": {} //if needed
    }
}

```

## Example messages:
```json
/*
{
    "type":"",
    "id":"",
    "auth": {},
    "payload":
    {

    }
}
*/

{
    "type":"AUTH.REGISTER_REQ",
    "id": "id",
    "auth": {},
    "payload":
    {
        "name": "Name of User",
        "email": "email of User",
        "username": "username",
        "password": "password", //to be sent over TLS
        "area": "area"
    }
}

{
    "type":"AUTH.REGISTER_REQ",
    "id":"id",
    "auth": {},
    "payload":
    {
        "user_id":"user_UUID4",
        "created_at": "time of creation"
    }
}

{
    "type":"AUTH.LOGIN_REQ",
    "id": "",
    "auth": {},
    "payload":
    {
        "username": "",
        "password": ""
    }
}

{
    "type":"AUTH.LOGIN_RES",
    "id": "",
    "auth": 
    {
        "token": "<>"
    },
    "payload":
    {
        
        "user": 
        {
            "user_id":"",
            "username":"",
            "name":"",
            "area":"",
            "is_driver":"",
            "rating":""

        }
        
    }
}

{
    "type":"AUTH.LOGOUT_REQ",
    "id": "",
    "auth": 
    {
        "token":
    },
    "payload":
    {
        
    }
}

{
    "type":"AUTH.LOGOUT_RES",
    "id": "",
    "auth": {},
    "payload":
    {
        "message": "Logout Succesful",
        "logged_out_at": ""
        
    }
}

```

## Payload definitions:
### 1. AUTH:
- AUTH.REGISTER_REQ:

```json
{
        "name": "Name of User",
        "email": "email of User",
        "username": "username",
        "password": "password", //to be sent over TLS
        "area": "area"
}
```
- AUTH.REGISTER_RES:
```json
{
        "user_id":"user_UUID4",
        "created_at": "time of creation"
}
```

- AUTH.LOGIN_REQ: 

```json
{
        
        "username": "username",
        "password": "password", //to be sent over TLS
}
```

- AUTH.LOGIN_RES: - HAS TOKEN IN AUTH FIELD!! important bc this will carry on with all the rest of the messages. we only want from authenticated users moving on from here

```json
{
        
       "user_id":"",
        "username":"",
        "name":"",
        "area":"",
        "is_driver":"",
        "rating":""

}
```

- AUTH.LOGOUT_REQ:
No payload

- AUTH.LOGOUT_RES:
```json
{
        "message": "Logout Succesful",
        "logged_out_at": ""
        
}
```

### 2. Profile:
- PROFILE.SET
```json
{

  "is_driver": "",
    "vehicle": 
    {
        "model": "",
        "make": "",
        "year": "",
        "color":"",
        "plate":""
    },
    "area": ""   
}
```

- PROFILE.GET
```json
{
    "is_driver": "",
    "car": 
    {
        "Model": "",
        "Make": "",
        "Year": "",
        "Color":""
    }

}
```

### 3. Schedule:
- SCHEDULE.SET
- SCHEDULE.GET
- SCHEDULE.SEARCH

### 4. Ride:
- RIDE.REQUEST
- RIDE.BROADCAST -> this will follow an EVT structure not REQ/RES structure
- RIDE.ACCEPT
- RIDE.DECLINE
- RIDE.MATCH -> this will follow an EVT structure not REQ/RES structure
- RIDE.CANCEL

### 5. Ratings:
- RATING.GET
- RATING.SET

### 6. Chat:
- CHAT.SEND
- CHAT.RCV
- CHAT.CLOSE