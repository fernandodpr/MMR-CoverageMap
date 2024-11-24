# MMR-CoverageMap

MMR-CoverageMap is a plugin designed to create a coverage map for a Meshtastic mesh network, visualizing node positions, coverage, and signal quality (SNR, RSSI) across a defined geographical area.

> ⚠ **Work in Progress**  
> This project is under active development and is not fully optimized. Current limitations include high resource consumption due to inefficient data storage and recalculations performed on each execution. Or even not working at all.

---

## Features

### Current Capabilities
- **Coverage Mapping**:  
  Generates a hexagonal grid map to visualize network coverage.
- **Dynamic Updates**:  
  Updates the coverage map in real-time based on incoming position data from the mesh network.
- **Matrix Integration**:  
  Allows users to request the latest map via a Matrix command (`!showmap`), with the map image sent directly to the Matrix room.

### Planned Features
- **Optimized Data Storage**:  
  Reduce memory usage by storing node data more efficiently, reusing grid data, and minimizing redundant calculations.
- **Multi-Map Support**:  
  Generate separate maps for individual nodes or groups while sharing the same grid structure to save resources.
- **Enhanced Map Details**:  
  Include additional metrics such as:
  - Signal-to-Noise Ratio (SNR)
  - Received Signal Strength Indicator (RSSI)
  - Altitude heatmaps
- **Interactive Map Export**:  
  Export interactive maps for better visualization using tools like Folium or Plotly.
- **Customizable Grid Resolution**:  
  Allow users to define hexagon sizes for different levels of detail.
- **Command Customization**:  
  Add support for additional commands to manage and query the plugin.

