package handlers

import (
	"database/sql"
	"encoding/csv"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

type AlprdHandler struct {
	db             *sql.DB
}

type PlateData struct {
	Plate      string    `json:"plate"`
	UUID       string    `json:"uuid"`
	ImageURL   string    `json:"image_url"`
	Confidence float64   `json:"confidence"`
	Timestamp  time.Time `json:"timestamp"`
	Location   string    `json:"location,omitempty"`
}


func NewAlprdHandler(db *sql.DB, streamChannel chan string) *AlprdHandler {
	handler := &AlprdHandler{
		db:            db,
	}
	return handler
}


// HandleAlprd processes incoming license plate detections
func (h *AlprdHandler) HandleAlprd(c *gin.Context) {
    var request struct {
        UUID       string  `json:"uuid"`
        Plate      string  `json:"plate"`
        Confidence float64 `json:"confidence"`
	    ImageURL   string  `json:"image_url"`
    }

    if err := c.ShouldBindJSON(&request); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request body"})
        return
    }
    // Removed undefined variable assignment
    plate := request.Plate
    confidence := request.Confidence
    fmt.Printf("Request Body: %+v\n", request)

    c.JSON(http.StatusCreated, gin.H{
        "message":    "Plate data processed successfully",
        "plate":      plate,
        "uuid":       request.UUID,
        "confidence": confidence,
        "imageUrl":   request.ImageURL,
    })
}











func (h *AlprdHandler) GetAllAlprd(c *gin.Context) {
    // Create data directory if it doesn't exist
    if err := os.MkdirAll("data", 0755); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{
            "error": fmt.Sprintf("Failed to create data directory: %v", err),
        })
        return
    }

    // Clean up previous CSV and SQL files
    csvFiles, err := filepath.Glob("data/alprd_*.csv")
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{
            "error": fmt.Sprintf("Failed to list CSV files: %v", err),
        })
        return
    }



    // Delete old files
    for _, file := range csvFiles {
        if err := os.Remove(file); err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{
                "error": fmt.Sprintf("Failed to delete file %s: %v", file, err),
            })
            return
        }
        log.Printf("Deleted previous file: %s", file)
    }

    // Generate filenames with timestamp
    timestamp := time.Now().Format("20060102_150405")
    csvFilename := "data/alprd.csv"
    sqlFilename := fmt.Sprintf("archive/sql-dumps/alprd_%s.sql", timestamp)

    // Create and write to CSV file
    csvCount, err := h.writeCSVFile(csvFilename)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{
            "error": fmt.Sprintf("Failed to create CSV file: %v", err),
        })
        return
    }

    // Create and write to SQL dump file
    sqlCount, err := h.writeSQLDump(sqlFilename)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{
            "error": fmt.Sprintf("Failed to create SQL dump file: %v", err),
        })
        return
    }

    if csvCount != sqlCount {
        log.Printf("Warning: CSV count (%d) doesn't match SQL count (%d)", csvCount, sqlCount)
    }

    log.Printf("Created new archive files with %d records: %s and %s", csvCount, csvFilename, sqlFilename)
    c.JSON(http.StatusOK, gin.H{"message": "Created new CSV file "})
}

func (h *AlprdHandler) writeCSVFile(filename string) (int, error) {
    csvFile, err := os.Create(filename)
    if err != nil {
        return 0, fmt.Errorf("failed to create CSV file: %v", err)
    }
    defer csvFile.Close()

    writer := csv.NewWriter(csvFile)
    defer writer.Flush()

    // Write headers
    headers := []string{"plate", "uuid", "imageurl"}
    if err := writer.Write(headers); err != nil {
        return 0, fmt.Errorf("failed to write CSV headers: %v", err)
    }

    // Query database for all records
    rows, err := h.db.Query("SELECT plate, uuid, imageurl FROM alprd")
    if err != nil {
        return 0, fmt.Errorf("database query failed: %v", err)
    }
    defer rows.Close()

    // Write data to CSV
    var count int
    for rows.Next() {
        var plate, uuid, imageurl string
        
        if err := rows.Scan(&plate, &uuid, &imageurl); err != nil {
            return 0, fmt.Errorf("failed to scan row: %v", err)
        }

        if err := writer.Write([]string{plate, uuid, imageurl}); err != nil {
            return 0, fmt.Errorf("failed to write CSV row: %v", err)
        }
        count++
    }

    if err := rows.Err(); err != nil {
        return 0, fmt.Errorf("row iteration error: %v", err)
    }

    return count, nil
}

func (h *AlprdHandler) writeSQLDump(filename string) (int, error) {
    sqlFile, err := os.Create(filename)
    if err != nil {
        return 0, fmt.Errorf("failed to create SQL file: %v", err)
    }
    defer sqlFile.Close()

    // Write SQL header
    _, err = sqlFile.WriteString("-- ALPRD Data Dump\n")
    if err != nil {
        return 0, fmt.Errorf("failed to write SQL header: %v", err)
    }
    
    _, err = sqlFile.WriteString("-- Generated at " + time.Now().Format(time.RFC3339) + "\n\n")
    if err != nil {
        return 0, fmt.Errorf("failed to write SQL header: %v", err)
    }

    // Query database for all records
    rows, err := h.db.Query("SELECT plate, uuid, imageurl FROM alprd")
    if err != nil {
        return 0, fmt.Errorf("database query failed: %v", err)
    }
    defer rows.Close()

    // Write data as SQL INSERT statements
    var count int
    for rows.Next() {
        var plate, uuid, imageurl string
        
        if err := rows.Scan(&plate, &uuid, &imageurl); err != nil {
            return 0, fmt.Errorf("failed to scan row: %v", err)
        }

        // Escape single quotes for SQL
        plate = strings.ReplaceAll(plate, "'", "''")
        imageurl = strings.ReplaceAll(imageurl, "'", "''")

        insertStmt := fmt.Sprintf(
            "INSERT INTO alprd (plate, uuid, imageurl) VALUES ('%s', '%s', '%s');\n",
            plate, uuid, imageurl,
        )

        if _, err := sqlFile.WriteString(insertStmt); err != nil {
            return 0, fmt.Errorf("failed to write SQL row: %v", err)
        }
        count++
    }

    if err := rows.Err(); err != nil {
        return 0, fmt.Errorf("row iteration error: %v", err)
    }

    return count, nil
}