import logging
import os  # Add this line to import the os module
from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash
from flask_bcrypt import Bcrypt
from flask_cors import CORS  
app = Flask(__name__)
CORS(app) 
CORS(app, resources={r"/api/*": {"origins": "http://frontend:3000"}})
# ", "methods": ["GET", "POST", "PUT", "DELETE"], "allow_headers": ["Content-Type", "Authorization"]}})
app.config['MONGO_URI'] = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/clinic_reservation.users')
mongo = PyMongo(app)
bcrypt = Bcrypt(app)

# my MongoDB collections 
users_collection = mongo.db.users
appointment_collection = mongo.db.appointment

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()

    # Check if the email already exists
    existing_user = users_collection.find_one({'email': data['email']})
    if existing_user:
        return jsonify({"msg": "User with this email already exists"}), 400  
    new_user = {
        'email': data['email'],
        'password': data['password'],
        'userType': 'doctor' if data.get('isDoctor') else 'patient',
    }


    users_collection.insert_one(new_user)
    print("User inserted successfully")
    return jsonify({"msg": "User registered successfully"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if 'email' not in data:
        return jsonify({"msg": "Email not provided"}), 400
    user = users_collection.find_one({'email': data['email']})

    if user and user['password'] == data['password']:
        return jsonify({"msg": "Login successful", "userType": user.get('userType', 'patient')}), 200
    else:
        return jsonify({"msg": "Invalid email or password"}), 401

@app.route('/api/set_schedule/<string:email>', methods=['POST'])
def set_schedule(email):
    data = request.get_json()

    doctor = users_collection.find_one({'email': email, 'userType': 'doctor'})

    if doctor:
        # the 'schedule' field is a list in the doctor's document
        if 'schedule' not in doctor:
            doctor['schedule'] = []

        new_slot = {
            'day': data.get('day'),
            'start_time': data.get('start_time'),
            'end_time': data.get('end_time')
        }

        doctor['schedule'].append(new_slot)

        users_collection.update_one({'email': email, 'userType': 'doctor'}, {'$set': doctor})

        return jsonify({"msg": "Schedule updated successfully"}), 200
    else:
        return jsonify({"msg": "User not found or not a doctor"}), 404
    

# ...

@app.route('/api/patient_appointment', methods=['GET', 'POST'])
def patient_appointment():
    # get all the doctors ro the list of doctors
    if request.method == 'GET':
        doctors = users_collection.find({'userType': 'doctor'}, {'email': 1})
        doctor_list = [doctor['email'] for doctor in doctors]
        return jsonify({"doctors": doctor_list}), 200

    elif request.method == 'POST':
        data = request.get_json()
        print(data)
        patient_email = data.get('patient_email')
        doctor_email = data.get('doctor_email')
        slot = {
            'day': data.get('day'),
            'start_time': data.get('start_time'),
            'end_time': data.get('end_time')
        }

        # Update the doctor's schedule to mark the slot booked
        result = users_collection.update_one(
            {'email': doctor_email, 'userType': 'doctor', 'schedule': {'$elemMatch': slot}},
            {'$set': {'schedule.$.booked': True}}
        )

        if result.modified_count > 0:
            # If the slot is booked successfully, save the appointment in the patient's document
            appointment_data = {
                'doctor_email': doctor_email,
                'day': slot['day'],
                'start_time': slot['start_time'],
                'end_time': slot['end_time']
            }

            appointmentCollectionData ={
                'patient_email': patient_email,
                'doctor_email': doctor_email,
                'day': slot['day'],
                'start_time': slot['start_time'],
                'end_time': slot['end_time'] 
            }

            appointment_collection.insert_one(appointmentCollectionData)

            # Update the patient's document to include the appointment
            users_collection.update_one(
                {'email': patient_email, 'userType': 'patient'},
                {'$push': {'appointments': appointment_data}}
            )
            return jsonify({"msg": "Slot booked successfully"}), 200
        else:
            return jsonify({"msg": "Slot not available or booking failed"}), 400


@app.route('/api/cancel_appointment', methods=['PUT'])
def cancel_appointment():
    data = request.get_json()
    patient_email = data.get('patient_email')
    doctor_email = data.get('doctor_email')
    slot = {
        'day': data.get('day'),
        'start_time': data.get('start_time'),
        'end_time': data.get('end_time')
    }

    # Update the doctor's schedule to mark the slot as available
    result = users_collection.update_one(
        {'email': doctor_email, 'userType': 'doctor', 'schedule': {'$elemMatch': slot}},
        {'$set': {'schedule.$.booked': False}}
    )

    if result.modified_count > 0:
        # If the slot is canceled successfully, remove the appointment from both collections
        users_collection.update_one(
    {'email': patient_email, 'userType': 'patient'},
    {'$pull': {'appointments': {'doctor_email': doctor_email, 'day': slot['day'],
     'start_time': slot['start_time'], 'end_time': slot['end_time']}}}
    )

        # Remove the appointment from the appointment collection
        appointment_collection.delete_one({
            'patient_email': patient_email,
            'doctor_email': doctor_email,
            'day': slot['day'],
            'start_time': slot['start_time'],
            'end_time': slot['end_time']
        })

        return jsonify({"msg": "Appointment canceled successfully"}), 200
    else:
        return jsonify({"msg": "Failed to cancel appointment. Appointment not found or invalid data"}), 400



@app.route('/api/view_patient_appointments/<string:email>', methods=['GET'])
def view_patient_appointments(email):
    patient = users_collection.find_one({'email': email, 'userType': 'patient'})

    if not patient:
        return jsonify({"msg": "Patient not found"}), 404

    # find all appointment of the specific patient
    appointments_cursor = appointment_collection.find({'patient_email': email})

    appointments = []
    for appointment in appointments_cursor:
        appointment['_id'] = str(appointment.get('_id'))
        appointments.append(appointment)

    return jsonify({"appointments": appointments}), 200

@app.route('/api/view_doctor_slots/<string:email>', methods=['GET'])
def view_doctor_slots(email):
    doctor = users_collection.find_one({'email': email, 'userType': 'doctor'})

    if not doctor:
        return jsonify({"msg": "Doctor not found"}), 404

    doctor_slots = doctor.get('schedule', [])

    

    return jsonify({"doctor_slots": doctor_slots}), 200

@app.route('/api/view_doctors', methods=['GET'])
def view_doctors():
    doctors = users_collection.find({'userType': 'doctor'}, {'email': 1})

    doctor_list = [doctor['email'] for doctor in doctors]

    return jsonify({"doctors": doctor_list}), 200

@app.route('/api/get_all_patient_emails', methods=['GET'])
def get_all_patient_emails():
    patients = mongo.db.users.find({'userType': 'patient'}, {'email': 1})

    patient_emails = [patient['email'] for patient in patients]

    return jsonify({"patientEmails": patient_emails}), 200

@app.route('/')
def index():
    return "Hello, World!"

if __name__ == '__main__':
    host = '0.0.0.0'
    port = 5000
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Running Flask app at http://{host}:{port}")
    app.run(debug=False, host=host, port=port)
