from plugins.base_plugin import BasePlugin
import h3

import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
from geopy.distance import geodesic


class Plugin(BasePlugin):
    plugin_name = "coveragemap"

    def __init__(self):
        super().__init__()
        # Convertir el string del YAML a una tupla de floats
        center_point_str = self.config.get("centerpoint", "1,1")
        self.center_point = tuple(map(float, center_point_str.split(',')))

        # Obtener el radio y la resolución con valores por defecto numéricos
        self.radius_km = float(self.config.get("radius", 50))  # Radio predeterminado: 50 km
        self.h3_resolution = int(self.config.get("h3_resolution", 10))  # Resolución predeterminada: 10

        # Inicializar el mapa
        self.map_data = self.initialize_map()

    def initialize_map(self):
        """
        Genera el mapa inicial con hexágonos, cobertura, SNR y RSSI.
        """
        hexagons = set()

        # Estimación inicial del bounding box en grados
        step_size = self.radius_km / 110.0  # Aproximación: 1° ~ 110 km
        lat_min = self.center_point[0] - step_size
        lat_max = self.center_point[0] + step_size
        lon_min = self.center_point[1] - step_size
        lon_max = self.center_point[1] + step_size

        for lat in range(int(lat_min * 10000), int(lat_max * 10000), 5):
            for lon in range(int(lon_min * 10000), int(lon_max * 10000), 5):
                hex_id = h3.latlng_to_cell(lat / 10000.0, lon / 10000.0, self.h3_resolution)
                hexagons.add(hex_id)
        # Convertir los hexágonos a polígonos
        hex_polygons = []
        for hex_id in hexagons:
            # Obtener las coordenadas del límite del hexágono
            hex_boundary = h3.cell_to_boundary(hex_id)  # Sin geo_json
            # Convertir las coordenadas en un polígono
            hex_polygons.append(Polygon(hex_boundary))

        # Crear un GeoDataFrame con campos para cobertura, SNR y RSSI
        gdf = gpd.GeoDataFrame({
            "geometry": hex_polygons,
            "coverage": [0] * len(hex_polygons),
            "snr": [None] * len(hex_polygons),  # Inicialmente vacío
            "rssi": [None] * len(hex_polygons),  # Inicialmente vacío
        })
        self.logger.debug(f"Mapa inicializado")

        return gdf
    def update_map(self, lat, lon, snr=None, rssi=None):
        """
        Actualiza el mapa con cobertura, SNR y RSSI en el hexágono correspondiente.
        """
        # Convertir latitud y longitud al identificador de celda H3
        hex_id = h3.latlng_to_cell(lat, lon, self.h3_resolution)

        # Iterar por el DataFrame para actualizar la cobertura, SNR y RSSI
        for idx, row in self.map_data.iterrows():
            # Convertir el identificador de celda H3 a un polígono
            hex_boundary = Polygon(h3.cell_to_boundary(hex_id))  

            # Comparar la geometría
            if hex_boundary.equals(row["geometry"]):
                self.map_data.at[idx, "coverage"] = 1  # Actualizar cobertura
                # Actualizar SNR y RSSI si están disponibles
                if snr is not None:
                    self.map_data.at[idx, "snr"] = snr
                if rssi is not None:
                    self.map_data.at[idx, "rssi"] = rssi
                break
    async def handle_meshtastic_message(self, packet, formatted_message, longname, meshnet_name):
        """
        Maneja los mensajes de Meshtastic y actualiza el mapa si cumplen con las condiciones.
        """
        return
        # Verificar que el mensaje contenga 'decoded'
        decoded = packet.get("decoded", {})
        if not decoded:
            return

        # Verificar que el mensaje sea de 'POSITION_APP'
        if decoded.get("portnum") != "POSITION_APP":
            return

        # Verificar que contenga un objeto 'position'
        position = decoded.get("position", {})
        if not position:
            return

        # Verificar que tenga 'precisionBits'
        if "precisionBits" not in position:
            return

        self.logger.debug(f"Se va a procesar la ubicación: {position}")

        # Extraer datos relevantes
        latitude = position.get("latitude")
        longitude = position.get("longitude")
        precision_bits = position.get("precisionBits")
        snr = packet.get("rxSnr", None)  # SNR si está disponible
        rssi = packet.get("rxRssi", None)  # RSSI si está disponible

        self.logger.debug(f"Datos procesados: Latitud={latitude}, Longitud={longitude}, PrecisionBits={precision_bits}, SNR={snr}, RSSI={rssi}")

        # Llamar a la función para actualizar el mapa
        if latitude is not None and longitude is not None:
            self.update_map(latitude, longitude, snr=snr, rssi=rssi)
    async def handle_room_message(self, room, event, full_message):
        """
        Maneja los mensajes de Matrix.
        """
        self.logger.debug(f"Mensaje recibido en la sala {room.room_id}: {full_message}")

        # Verificar si el mensaje contiene "!showmap"
        if "!showmap" in full_message.lower():
            self.logger.debug("Comando '!showmap' detectado en el mensaje. Generando el mapa.")
            try:
                await self.send_map(room.room_id)
            except Exception as e:
                self.logger.error(f"Error al enviar el mapa: {e}")
        else:
            self.logger.debug("Mensaje no reconocido o sin acción.")


    async def send_map(self, room_id):
        """
        Genera y envía el mapa actual como imagen a Matrix.
        """
        self.logger.debug("Generando el mapa de cobertura...")
        try:
            # Generar el mapa como imagen
            fig, ax = plt.subplots(1, 1, figsize=(10, 10))
            self.map_data.plot(ax=ax, column="coverage", cmap="coolwarm", legend=True)
            plt.title("Mapa de Cobertura")
            plt.xlabel("Longitud")
            plt.ylabel("Latitud")

            # Guardar la imagen
            image_path = "/tmp/coveragemap.png"
            plt.savefig(image_path)
            plt.close()
            self.logger.debug(f"Mapa de cobertura guardado en {image_path}")

            # Leer y enviar la imagen a Matrix
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                self.logger.debug("Enviando el mapa a Matrix...")
                await self.send_matrix_message(
                    room_id, "Mapa de cobertura actualizado. Imagen generada."
                )
        except Exception as e:
            self.logger.error(f"Error al generar o enviar el mapa: {e}")
