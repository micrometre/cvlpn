import beanstalkc

# Beanstalkd server details
BEANSTALKD_HOST = 'localhost'  # Change if your server is elsewhere
BEANSTALKD_PORT = 11300

def put_job(tube_name, job_data):
    """Puts a job onto the Beanstalkd queue."""
    try:
        beanstalk = beanstalkc.Connection(host=BEANSTALKD_HOST, port=BEANSTALKD_PORT)
        beanstalk.use(tube_name)
        job_id = beanstalk.put(job_data)
        print(f"Job {job_id} put into tube '{tube_name}'")
        beanstalk.close()
        return job_id
    except beanstalkc.SocketError as e:
        print(f"Error connecting to Beanstalkd: {e}")
        return None

def get_job(tube_name):
    """Gets a job from the Beanstalkd queue."""
    try:
        beanstalk = beanstalkc.Connection(host=BEANSTALKD_HOST, port=BEANSTALKD_PORT)
        beanstalk.watch(tube_name)
        job = beanstalk.reserve(timeout=5)  # Wait for 5 seconds

        if job:
            job_data = job.body
            print(f"Job {job.jid} received from tube '{tube_name}': {job_data}")
            job.delete() # important: delete the job after processing
            beanstalk.close()
            return job_data
        else:
            print(f"No job available in tube '{tube_name}' within timeout.")
            beanstalk.close()
            return None

    except beanstalkc.SocketError as e:
        print(f"Error connecting to Beanstalkd: {e}")
        return None

def peek_ready(tube_name):
    """Peek at the next ready job without reserving it."""
    try:
        beanstalk = beanstalkc.Connection(host=BEANSTALKD_HOST, port=BEANSTALKD_PORT)
        beanstalk.use(tube_name)
        ready_job = beanstalk.peek_ready()

        if ready_job:
            print(f"Peeked ready job {ready_job.jid} from tube '{tube_name}': {ready_job.body}")
            beanstalk.close()
            return ready_job.body
        else:
            print(f"No ready jobs in tube '{tube_name}'.")
            beanstalk.close()
            return None

    except beanstalkc.SocketError as e:
        print(f"Error connecting to Beanstalkd: {e}")
        return None

if __name__ == "__main__":
    tube = "alpr_tube"
    job_payload = b"Hello, Beanstalkd!"

    # Put a job onto the queue
    put_job(tube, job_payload)

    # Peek at the ready job
    peek_ready(tube)

    # Get and process a job from the queue
    received_job = get_job(tube)

    if received_job:
        print(f"Processed job: {received_job.encode()}") #decode bytes back to string.

    # Put another job onto the queue, to demonstrate multiple jobs
    put_job(tube, b"Another job")
    get_job(tube)