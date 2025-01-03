# Communal Savings App

This project is a Flask application designed to manage communal savings for users. It allows users to create savings groups, track balances, and maintain transaction histories. The application features user roles within groups, enabling better management and organization of savings activities.

## Features

- User registration and authentication
- Creation and management of savings groups
- User roles within groups (e.g., admin, member)
- Transaction history tracking for each group
- Current balance display for savings groups
- Responsive design using Tailwind CSS

## Project Structure

```
communal-savings-app
├── templates
│   ├── acceuil.html          # Welcome page after login
│   ├── admin
│   │   └── index.html        # Admin dashboard
│   ├── connexion.html         # User login form
│   ├── index.html            # Landing page for sign up/login
│   ├── inscription.html       # User registration form
│   ├── group.html            # Manage savings groups
│   ├── transaction.html       # Transaction history for groups
│   └── balance.html          # Current balance of savings groups
├── flask_app.py              # Main application file
├── requirements.txt          # Project dependencies
└── README.md                 # Project documentation
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd communal-savings-app
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up the database:
   - Ensure you have SQLite installed.
   - The database will be created automatically when you run the application for the first time.

## Usage

1. Run the application:
   ```
   python flask_app.py
   ```

2. Open your web browser and navigate to `http://127.0.0.1:5000`.

3. Create an account or log in to access the application features.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.