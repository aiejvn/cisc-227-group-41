import logging

from app import create_app
from app.routes.rentals import start_reminder_timer

app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Daily return reminders: once at startup, then every 24 hours.
    # The reloader is off so only one process (and one timer) runs.
    start_reminder_timer()
    
    app.run(debug=True, use_reloader=False)
