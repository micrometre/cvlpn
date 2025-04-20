import json
import beanstalkc
from datetime import datetime

# Beanstalkd configuration (should match your producer config)
BEANSTALKD_HOST = 'localhost'
BEANSTALKD_PORT = 11300
BEANSTALKD_TUBE = 'license_plates'

def process_plate_message(plate_data):
    """Process a single license plate detection"""
    print("\n📋 Received plate detection:")
    print(f"uuid: {plate_data['uuid']}")
    print(f"Plate: {plate_data['plate']}")
    print(f"Timestamp: {plate_data['timestamp']}")
    print(f"Video Source: {plate_data['video_source']}")
    print(f"Frame Position: {plate_data['position']}")
    print(f"Frame Number: {plate_data['frame_num']}")
    
    # Add your custom processing logic here
    # For example: database storage, API calls, alerts, etc.
    
    # Example: Write to a log file
    with open("plate_detections.log", "a") as log_file:
        log_entry = f"{datetime.now().isoformat()},{plate_data['plate']},{plate_data['video_source']}\n"
        log_file.write(log_entry)

def consume_plates():
    print(f"🚀 Starting license plate consumer on {BEANSTALKD_HOST}:{BEANSTALKD_PORT}")
    print(f"📭 Watching tube: {BEANSTALKD_TUBE}")
    
    try:
        # Connect to Beanstalkd
        beanstalk = beanstalkc.Connection(
            host=BEANSTALKD_HOST,
            port=BEANSTALKD_PORT
        )
        
        # Watch our specific tube
        beanstalk.watch(BEANSTALKD_TUBE)
        
        print("🛎️ Consumer ready. Waiting for plate detections...")
        
        while True:
            # Wait for a job with timeout (in seconds)
            job = beanstalk.reserve(timeout=60)
            
            if job:
                try:
                    # Parse the JSON message
                    plate_data = json.loads(job.body)
                    process_plate_message(plate_data)
                    
                    # Delete the job from queue after successful processing
                    job.delete()
                except json.JSONDecodeError:
                    print("⚠️ Error decoding JSON message")
                    job.bury()  # Bury invalid messages
                except Exception as e:
                    print(f"⚠️ Error processing message: {str(e)}")
                    job.bury()  # Bury failed messages
            else:
                # No message received within timeout period
                print("⏳ No messages received in the last 60 seconds...")
                
    except KeyboardInterrupt:
        print("\n🛑 Consumer stopped by user")
    except Exception as e:
        print(f"🔴 Error in consumer: {str(e)}")
    finally:
        if 'beanstalk' in locals():
            beanstalk.close()

if __name__ == "__main__":
    consume_plates()
if __name__ == "__main__":
    consume_plates()