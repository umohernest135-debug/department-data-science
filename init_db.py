import sqlite3

connection = sqlite3.connect("database.db")
cursor = connection.cursor()

with open("schema.sql", "r") as f:
    cursor.executescript(f.read())

connection.commit()
connection.close()

print("Database created successfully!")
