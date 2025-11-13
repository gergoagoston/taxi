Porto Taxi Heatmap VisualizerThis is an interactive web application built with Panel and Folium to visualize taxi trips in Porto, Portugal. 
It queries a PostgreSQL/PostGIS database to fetch trip data and displays it as an interactive heatmap on a map, allowing users to filter by date, time, and location type.
Features Interactive Heatmap: Displays the density of taxi trips.Map Style: Toggle between 'Light' (CartoDB Positron) and 'Dark' (CartoDB dark_matter) map tiles.

Trip Mode: Filter data for 'Pickup', 'Dropoff', or 'Both' locations.
Date Range: Select a start and end date for the analysis.
Hour Range: Use a slider to filter trips by the hour of the day.
Day Type: Include or exclude 'Weekday' or 'Weekend' trips.
Grid Layer: An invisible grid layer provides tooltips showing the exact trip count when you hover over a dense area.

Project StructureThe project is organized into several files for better maintainability:
    .
    ├── app.py                 # Main application, runs the server
    ├── widgets.py             # Defines all UI components (buttons, sliders)
    ├── database.py            # Handles all database connections and query building
    ├── config.py              # Stores database connection credentials
    ├── setup.sql              # SQL script to create the necessary table
    ├── run.bat                # Windows batch file to automate setup and launch
    ├── style.css              # All CSS styling for the application
    └── README.md              # This file

Setup & InstallationFollow these steps to get the application running on your local machine.
1. PrerequisitesPython 3.7+PostgreSQL Server with the PostGIS extension.A database (e.g., taxis_porto) that contains the original trip table with taxi polyline data.
The following Python libraries: pip install panel folium pandas psycopg2-binary
Configure Database CredentialsBefore running, you must edit the config.py file to match your PostgreSQL server details:# config.p

2. Database Setup (One-Time Step)The application runs on a simplified table named trip_simple for performance. You must create this table by running the setup.sql script in PgAdmin. You only need to do this once. 

3. Running the Application
If you have already completed the database setup, you can launch the app at any time using this command: 

panel serve app.py --show

This will start the server and open the application in your default web browser.