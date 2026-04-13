import React, { useState, useEffect } from 'react';
import './tf.css';

// 1. The Predefined Metadata Sets (No vehicle types, just pure physics)
// Each set contains exactly 4 metadata objects for [North, South, East, West]
const METADATA_SETS = [
  // Set 1: North has a high-speed EV, South has a stopped EV
  [ { speed: 108, dist: 30, score: 9 }, { speed: 0, dist: 0, score: 5 }, { speed: 40, dist: 100, score: 0 }, { speed: 0, dist: 0, score: 0 } ],
  // Set 2: East has a slow EV, North has normal traffic
  [ { speed: 60, dist: 150, score: 0 }, { speed: 0, dist: 0, score: 0 }, { speed: 20, dist: 50, score: 8 }, { speed: 45, dist: 80, score: 0 } ],
  // Set 3: 4-Way Tie Scenario (All EVs moving fast)
  [ { speed: 80, dist: 200, score: 10 }, { speed: 80, dist: 100, score: 10 }, { speed: 80, dist: 300, score: 10 }, { speed: 80, dist: 400, score: 10 } ],
  // Set 4: Empty intersection except for West
  [ { speed: 0, dist: 0, score: 0 }, { speed: 0, dist: 0, score: 0 }, { speed: 0, dist: 0, score: 0 }, { speed: 90, dist: 120, score: 9 } ],
  // Set 5: Normal traffic only (No EVs)
  [ { speed: 40, dist: 50, score: 0 }, { speed: 30, dist: 20, score: 0 }, { speed: 50, dist: 100, score: 0 }, { speed: 45, dist: 80, score: 0 } ]
];

const ROADS = ['North', 'South', 'East', 'West'];

export default function TrafficDashboard() {
  // Store the actual image files/URLs uploaded by the user
  const [uploadedImages, setUploadedImages] = useState({ North: null, South: null, East: null, West: null });
  
  const [activeQueue, setActiveQueue] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [timer, setTimer] = useState(0);
  const [isRunning, setIsRunning] = useState(false);

  // Handle file uploads and create local URLs to display the images
  const handleImageUpload = (road, event) => {
    const file = event.target.files[0];
    if (file) {
      setUploadedImages(prev => ({ ...prev, [road]: URL.createObjectURL(file) }));
    }
  };

  // 2. The Math Engine (Now uses uploaded images + random metadata)
  // 2. The Real API Integration Engine
  const runSimulation = async () => {
    setIsRunning(false);
    setTimer(0);

    // If they haven't uploaded images, warn them
    if (!uploadedImages.North && !uploadedImages.South && !uploadedImages.East && !uploadedImages.West) {
      alert("Please upload at least one camera feed!");
      return;
    }

    // 1. Prepare the JSON Metadata payload
    // In a real app, this would come from radar/GPS. For now, we simulate the physics.
    const mockPhysics = [
      { road: "North", speed_kmh: 60, distance_m: 200, emergency_score: 9 },
      { road: "South", speed_kmh: 0, distance_m: 0, emergency_score: 0 },
      { road: "East", speed_kmh: 40, distance_m: 100, emergency_score: 5 },
      { road: "West", speed_kmh: 0, distance_m: 0, emergency_score: 0 }
    ];

    // 2. Build the exact multipart/form-data payload your FastAPI expects
    const formData = new FormData();
    formData.append('metadata', JSON.stringify(mockPhysics));

    // Helper to fetch the local blob URL and turn it back into a File object for the API
    const appendImageToForm = async (roadName, fieldName) => {
      if (uploadedImages[roadName]) {
        const response = await fetch(uploadedImages[roadName]);
        const blob = await response.blob();
        formData.append(fieldName, blob, `${roadName.toLowerCase()}_feed.jpg`);
      } else {
        // Create a tiny blank image to prevent the server from crashing on missing files
        const blankCanvas = document.createElement('canvas');
        blankCanvas.width = 10; blankCanvas.height = 10;
        const blankBlob = await new Promise(res => blankCanvas.toBlob(res, 'image/jpeg'));
        formData.append(fieldName, blankBlob, `blank_${roadName.toLowerCase()}.jpg`);
      }
    };

    await appendImageToForm('North', 'north_image');
    await appendImageToForm('South', 'south_image');
    await appendImageToForm('East', 'east_image');
    await appendImageToForm('West', 'west_image');

    try {
      // 3. Send it to your FastAPI server!
      // NOTE: Replace this URL with your actual Lightning AI Port 8000 URL if needed
      const response = await fetch('https://8000-01kncth8reb3cw0hnb1etrhxx8.cloudspaces.litng.ai/detect_v2', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error("Server rejected the payload");

      const data = await response.json();
      
      // 4. Map the Python backend's exact response directly into our UI state
      const processedQueue = data.raw_queue.map(item => ({
        road: item.road,
        type: item.emergency_spotted ? 'EV Detected' : 'Normal',
        speed: item.metadata.speed_kmh,
        dist: item.metadata.distance_m,
        score: item.metadata.emergency_score,
        isEV: item.emergency_spotted,
        priority: item.priority_score,
        rawEta: item.eta_seconds === "N/A" ? 999 : item.eta_seconds,
        imageSrc: uploadedImages[item.road] // Keep our local image for the UI
      }));

      const newSchedule = data.emergency_schedule.map(s => ({
        road: s.road,
        start: s.green_light_start_sec,
        end: s.green_light_end_sec
      }));

      setActiveQueue(processedQueue);
      setSchedule(newSchedule);
      setIsRunning(true);

    } catch (error) {
      console.error("API Error:", error);
      alert("Failed to connect to the YOLO backend. Is the server running?");
    }
  };

  // 3. System Clock
  useEffect(() => {
    let interval;
    if (isRunning) {
      interval = setInterval(() => setTimer(prev => prev + 1), 1000);
    }
    return () => clearInterval(interval);
  }, [isRunning]);

  const getLightColor = (roadName) => {
    const roadSchedule = schedule.find(s => s.road === roadName);
    if (!roadSchedule) return 'red'; 
    if (timer >= roadSchedule.start && timer < roadSchedule.end) return 'green';
    return 'red';
  };

  // 4. Custom UI for displaying the uploaded images inside the intersection
  const VehicleImage = ({ vehicle }) => {
    if (!vehicle || !vehicle.imageSrc) return null;
    
    // Draw a red bounding box if it's an EV, yellow if it's a normal vehicle
    const borderColor = vehicle.isEV ? 'border-red-500' : 'border-yellow-500';
    const glow = vehicle.isEV ? 'drop-shadow-[0_0_8px_rgba(239,68,68,0.8)]' : '';

    return (
      <div className="flex flex-col items-center">
        <img 
            src={vehicle.imageSrc} 
            alt="Detected" 
            style={{ width: '60px', height: '60px', objectFit: 'cover', borderRadius: '4px', borderWidth: '3px' }}
            className={`border-solid ${borderColor} ${glow}`}
        />
        {vehicle.isEV && <div className="text-[10px] bg-red-600 text-white px-1 mt-1 font-bold rounded">ETA: {Math.round(vehicle.rawEta)}s</div>}
      </div>
    );
  };

  return (
    <div className="td-container">
      <div className="td-layout">
        
        {/* LEFT: Controls & Visualizer */}
        <div className="td-visualizer-col" style={{ width: '100%' }}>
          
          {/* File Uploaders */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', width: '100%', marginBottom: '20px' }}>
            {ROADS.map(road => (
                <div key={road} style={{ backgroundColor: '#111827', padding: '10px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '5px' }}>{road} Camera Feed:</label>
                    <input type="file" accept="image/*" onChange={(e) => handleImageUpload(road, e)} style={{ fontSize: '12px', width: '100%' }} />
                </div>
            ))}
          </div>

          <button onClick={runSimulation} className="td-sim-btn" style={{ width: '100%' }}>
            PROCESS INTERSECTION
          </button>

          <div className="td-intersection">
            <div className="td-road-vertical" />
            <div className="td-road-horizontal" />
            <div className="td-center-box" />

            {/* Render Lights & Images */}
            <div className="pos-n-light"><TrafficLight color={getLightColor('North')} /></div>
            <div className="pos-n-car"><VehicleImage vehicle={activeQueue.find(v => v.road === 'North')} /></div>

            <div className="pos-s-light"><TrafficLight color={getLightColor('South')} /></div>
            <div className="pos-s-car"><VehicleImage vehicle={activeQueue.find(v => v.road === 'South')} /></div>

            <div className="pos-e-light"><TrafficLight color={getLightColor('East')} /></div>
            <div className="pos-e-car"><VehicleImage vehicle={activeQueue.find(v => v.road === 'East')} /></div>

            <div className="pos-w-light"><TrafficLight color={getLightColor('West')} /></div>
            <div className="pos-w-car"><VehicleImage vehicle={activeQueue.find(v => v.road === 'West')} /></div>
          </div>
          
          <div className="td-clock">System Clock: {timer}s</div>
        </div>

        {/* RIGHT: Live Queue Data */}
        <div className="td-data-col">
          <h2 className="td-header-blue">Live Priority Queue</h2>
          {activeQueue.length === 0 ? (
            <p className="td-empty-msg">Upload images and process feeds to see data...</p>
          ) : (
            <div className="td-queue-list">
              {activeQueue.map((v, i) => (
                <div key={i} className={`td-queue-item ${v.isEV ? 'ev' : 'normal'}`}>
                  <div>
                    <span className="td-q-road">{v.road}</span>
                    <span className="td-q-type">Score: {v.score} ({v.speed}km/h)</span>
                  </div>
                  {v.isEV ? (
                    <div style={{textAlign: 'right'}}>
                      <div className="td-q-score">Priority: {v.priority.toFixed(1)}</div>
                      <div className="td-q-eta">ETA: {v.rawEta.toFixed(1)}s</div>
                    </div>
                  ) : (
                    <div className="td-q-yield">Yielding</div>
                  )}
                </div>
              ))}
            </div>
          )}

          <h2 className="td-header-green">Green Light Schedule</h2>
          {schedule.length === 0 ? (
             <p className="td-empty-msg">No emergencies scheduled.</p>
          ) : (
             <div className="td-schedule-list">
               {schedule.map((s, i) => (
                 <div key={i} className="td-schedule-row">
                   <span className="td-s-road">{s.road}</span>
                   <span className="td-s-time">{Math.round(s.start)}s → {Math.round(s.end)}s</span>
                 </div>
               ))}
             </div>
          )}
        </div>

      </div>
    </div>
  );
}

// Light Component (kept from previous)
const TrafficLight = ({ color }) => (
    <div className="td-traffic-light">
      <div className={`td-bulb red ${color === 'red' ? 'active' : 'dim'}`} />
      <div className={`td-bulb yellow ${color === 'yellow' ? 'active' : 'dim'}`} />
      <div className={`td-bulb green ${color === 'green' ? 'active' : 'dim'}`} />
    </div>
);