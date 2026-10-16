# Skills Mapping React Native App

This is an Expo app that sends a resume PDF or pasted text to the Skills Mapping recommendation API and displays ranked course recommendations.

## Setup

1. Install dependencies:

```powershell
cd mobile
npm install
```

2. Start the Expo app:

```powershell
npm start
```

3. Use Expo Go on your device or an emulator.

## API configuration

Update `API_URL` in `App.js` to point to your backend server if it is not running on `http://10.0.2.2:8000`.

- Android emulator: `http://10.0.2.2:8000`
- iOS simulator / web: `http://localhost:8000`
- Physical device: local machine IP, e.g. `http://192.168.1.12:8000`
