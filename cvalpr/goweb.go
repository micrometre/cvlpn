package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/beanstalkd/go-beanstalk"
	"github.com/gin-gonic/gin"
)

type PlateData struct {
	UUID        string    `json:"uuid"`
	Plate       string    `json:"plate"`
	Timestamp   string    `json:"timestamp"`
	VideoSource string    `json:"video_source"`
	Position    []int     `json:"position"`
	FrameNum    int       `json:"frame_num"`
	ImagePath   string    `json:"image_path"`
}

type DetectionStore struct {
	sync.RWMutex
	detections []PlateData
}

const (
	beanstalkHost = "localhost:11300"
	beanstalkTube = "license_plates"
	logFile       = "plate_detections.log"
	webPort       = "8080"
)

var (
	store = DetectionStore{detections: make([]PlateData, 0)}
)

func processPlateMessage(data PlateData) {
	fmt.Println("\n📋 Received plate detection:")
	fmt.Printf("UUID: %s\n", data.UUID)
	fmt.Printf("Plate: %s\n", data.Plate)
	fmt.Printf("Timestamp: %s\n", data.Timestamp)
	fmt.Printf("Video Source: %s\n", data.VideoSource)
	fmt.Printf("Position: %v\n", data.Position)
	fmt.Printf("Frame Number: %d\n", data.FrameNum)
	fmt.Printf("Image Path: %s\n", data.ImagePath)

	// Add to in-memory store
	store.Lock()
	store.detections = append(store.detections, data)
	store.Unlock()

	// Log to file
	logEntry := fmt.Sprintf("%s,%s,%s,%s\n",
		time.Now().Format(time.RFC3339),
		data.UUID,
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

func setupRouter() *gin.Engine {
	r := gin.Default()

	// ALPR API routes
	api := r.Group("/api/alpr")
	{
		api.GET("/detections", getDetections)
		api.GET("/detections/:uuid", getDetectionByUUID)
		api.GET("/search", searchDetections)
	}

	// Image serving route
	r.Static("/images", "./plate_images")

	// Web interface
	r.GET("/", func(c *gin.Context) {
		c.File("./web/index.html")
	})
	r.Static("/assets", "./web/assets")

	return r
}

func getDetections(c *gin.Context) {
	store.RLock()
	defer store.RUnlock()
	c.JSON(http.StatusOK, store.detections)
}

func getDetectionByUUID(c *gin.Context) {
	uuid := c.Param("uuid")
	store.RLock()
	defer store.RUnlock()

	for _, detection := range store.detections {
		if detection.UUID == uuid {
			c.JSON(http.StatusOK, detection)
			return
		}
	}

	c.JSON(http.StatusNotFound, gin.H{"error": "Detection not found"})
}

func searchDetections(c *gin.Context) {
	query := c.Query("q")
	if query == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Missing search query"})
		return
	}

	store.RLock()
	defer store.RUnlock()

	results := make([]PlateData, 0)
	for _, detection := range store.detections {
		if strings.Contains(detection.Plate, query) {
			results = append(results, detection)
		}
	}

	c.JSON(http.StatusOK, results)
}

func main() {
	// Create required directories
	if err := os.MkdirAll("plate_images", 0755); err != nil {
		log.Fatalf("🔴 Error creating plate_images directory: %v", err)
	}
	if err := os.MkdirAll("web/assets", 0755); err != nil {
		log.Fatalf("🔴 Error creating web directory: %v", err)
	}

	// Create log file if it doesn't exist
	if _, err := os.Stat(logFile); os.IsNotExist(err) {
		_, err := os.Create(logFile)
		if err != nil {
			log.Fatalf("🔴 Error creating log file: %v", err)
		}
	}

	// Start Beanstalkd consumer in background
	go consumePlates()

	// Start web server
	r := setupRouter()
	fmt.Printf("🌐 Web server running on port %s\n", webPort)
	log.Fatal(r.Run(":" + webPort))
}