PITCH & BREW — FULL FLASK APP
=============================

INCLUDED
- Premium responsive customer website.
- Intro sequence with canvas-drawn bat swing, ball impact cue, red ball flight and golden trail.
- Booking form with server-side validation and schedule availability API.
- Repeating 1/2/3-day booking availability checks.
- Cafe menu/cart and order submission.
- WhatsApp booking and cafe handoff to 0302-5122000.
- Admin login, schedule paste/update, booking status management, recent cafe orders.
- SQLite database automatically created on first run.
- Offline connection banner.

RUN LOCALLY ON WINDOWS
1. Install Python 3.11+.
2. Open this folder in VS Code.
3. In VS Code terminal:
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   set PITCHBREW_ADMIN_PASSWORD=choose-a-strong-password
   py app.py
4. Open http://127.0.0.1:5000
5. Admin panel: http://127.0.0.1:5000/admin
   If you did not set PITCHBREW_ADMIN_PASSWORD, the development default is change-me.
   Change it before public deployment.

DEPLOYMENT
- Use a Flask-capable host (PythonAnywhere, Render, etc.), not static-only GitHub Pages.
- Install requirements.txt. Use app:app as the WSGI/WSGI entry target as appropriate.
- Set environment variables PITCHBREW_ADMIN_PASSWORD and PITCHBREW_SECRET.
- Keep the SQLite database persistent; on serverless/ephemeral hosts use a persistent database instead.
- HTTPS is required for production.
- This package is a fresh standalone project. It does not overwrite or migrate an existing Pitch & Brew backend/database.
- Do not publish with the default admin password.

IMPORTANT BOOKING NOTE
If no schedule is uploaded for a date, the frontend offers suggested times but warns the customer that availability needs confirmation. Existing booking requests are checked server-side. The admin should paste the real current schedule before relying on automatic availability.

ANIMATION NOTE
The bat/ball intro is canvas-rendered, not a pre-recorded photorealistic video or a scanned 3D model. For true film-quality realism, use licensed bat/ball video or high-quality 3D assets. The included intro is integrated into the full app, not a separate demo.
