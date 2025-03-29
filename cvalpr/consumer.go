package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/beanstalkd/go-beanstalk"
)

type PlateData struct {
	UUID        string    `json:"uuid"`
	Plate       string    `json:"plate"`
	Timestamp   string    `json:"timestamp"`
	VideoSource string    `json:"video_source"`
	Position    []int     `json:"position"`
	FrameNum    int       `json:"frame_num"`
}

const (
	beanstalkHost = "localhost:11300"
	beanstalkTube = "license_plates"
	logFile       = "plate_detections.log"
)

func processPlateMessage(data PlateData) {
	fmt.Println("\n📋 Received plate detection:")
	fmt.Printf("UUID: %s\n", data.UUID)
	fmt.Printf("Plate: %s\n", data.Plate)
	fmt.Printf("Timestamp: %s\n", data.Timestamp)
	fmt.Printf("Video Source: %s\n", data.VideoSource)
	fmt.Printf("Position: %v\n", data.Position)
	fmt.Printf("Frame Number: %d\n", data.FrameNum)

	// Log to file
	logEntry := fmt.Sprintf("%s,%s,%s\n", 
		time.Now().Format(time.RFC3339), 
		data.Plate, 
		data.VideoSource)

	f, err := os.OpenFile(logFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("⚠️ Error opening log file: %v", err)
		return
	}
	defer f.Close()

	if _, err := f.WriteString(logEntry); err != nil {
		log.Printf("⚠️ Error writing to log file: %v", err)
	}
}

func consumePlates() {
	fmt.Printf("🚀 Starting license plate consumer on %s\n", beanstalkHost)
	fmt.Printf("📭 Watching tube: %s\n", beanstalkTube)

	// Connect to Beanstalkd
	conn, err := beanstalk.Dial("tcp", beanstalkHost)
	if err != nil {
		log.Fatalf("🔴 Failed to connect to Beanstalkd: %v", err)
	}
	defer conn.Close()

	// Watch our tube
	tube := beanstalk.NewTubeSet(conn, beanstalkTube)
	fmt.Println("🛎️ Consumer ready. Waiting for plate detections...")

	for {
		// Reserve with timeout (60 seconds)
		id, body, err := tube.Reserve(60 * time.Second)
		if err != nil {
			if err.Error() == "reserve-with-timeout: timeout" {
				fmt.Println("⏳ No messages received in the last 60 seconds...")
				continue
			}
			log.Printf("⚠️ Error reserving job: %v", err)
			continue
		}

		var plateData PlateData
		if err := json.Unmarshal(body, &plateData); err != nil {
			log.Printf("⚠️ Error decoding JSON message: %v", err)
			conn.Bury(id, 0) // Bury invalid message
			continue
		}

		processPlateMessage(plateData)

		// Delete the job after successful processing
		if err := conn.Delete(id); err != nil {
			log.Printf("⚠️ Error deleting job: %v", err)
		}
	}
}

func main() {
	// Create log file if it doesn't exist
	if _, err := os.Stat(logFile); os.IsNotExist(err) {
		_, err := os.Create(logFile)
		if err != nil {
			log.Fatalf("🔴 Error creating log file: %v", err)
		}
	}

	consumePlates()
}