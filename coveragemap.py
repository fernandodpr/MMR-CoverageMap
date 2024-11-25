from plugins.base_plugin import BasePlugin
import h3

import geopandas as gpd
from shapely.geometry import Polygon
import folium
from shapely.geometry import mapping
import matplotlib.pyplot as plt
from geopy.distance import geodesic


class Plugin(BasePlugin):
    plugin_name = "coveragemap"

    def __init__(self):
        super().__init__()
        # Obtener configuración del plugin desde el nivel correcto
        plugin_config = self.config.get("plugins", {}).get("coveragemap", {})
        self.logger.debug(f"[CONFIG_CONTENT] Contenido del plugin coveragemap: {plugin_config}")

        # Obtener el centro desde la configuración, con valor predeterminado
        center_point_str = self.config.get("centerpoint", "1,-1")
        try:
            self.center_point = tuple(map(float, center_point_str.split(',')))
        except Exception as e:
            self.logger.error(f"[CONFIG_ERROR] Error al interpretar 'centerpoint': {center_point_str}. Usando valor predeterminado (1.0, 1.0). Error: {e}")
            self.center_point = (1.0, 1.0)

        # Obtener el radio y la resolución con valores por defecto
        try:
            self.radius_km = float(self.config.get("radius", 5))  # Radio predeterminado: 2 km
        except Exception as e:
            self.logger.error(f"[CONFIG_ERROR] Error al interpretar 'radius'. Usando valor predeterminado (2). Error: {e}")
            self.radius_km = 2

        try:
            self.h3_resolution = int(self.config.get("h3_resolution", 8))  # Resolución predeterminada: 2
        except Exception as e:
            self.logger.error(f"[CONFIG_ERROR] Error al interpretar 'h3_resolution'. Usando valor predeterminado (2). Error: {e}")
            self.h3_resolution = 2

        # Log detallado de la configuración cargada
        self.logger.info("[CONFIGURATION] Configuración cargada:")
        self.logger.info(f"  Centro (lat, lon): {self.center_point}")
        self.logger.info(f"  Radio (km): {self.radius_km}")
        self.logger.info(f"  Resolución H3: {self.h3_resolution}")
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

        if "!showmap" in full_message.lower():
            self.logger.debug("Comando '!showmap' detectado en el mensaje. Generando el mapa interactivo.")
            try:
                # Llamada correcta al método
                self.export_map_as_html()  # Usará la ruta predeterminada ./coveragemap.html
                self.logger.debug("Mapa interactivo generado correctamente.")

                # Enviar mensaje a Matrix con un enlace al archivo
                await self.send_matrix_message(
                    room.room_id,
                    "El mapa de cobertura se ha generado: [Ver mapa interactivo](file://./coveragemap.html)"
                )
            except Exception as e:
                self.logger.error(f"Error al generar o enviar el mapa: {e}")
        else:
            self.logger.debug("Mensaje no reconocido o sin acción.")

    async def send_map(self, room_id):
        """
        Genera el mapa de cobertura como imagen, lo guarda en el sistema y lo envía a Matrix.
        """
        self.logger.debug("Iniciando el proceso para generar y enviar el mapa de cobertura.")

        try:
            # Paso 1: Generar el mapa
            self.logger.debug("Generando la figura del mapa...")
            self.logger.debug(f"Cantidad de celdas en el mapa: {len(self.map_data)}")
            fig, ax = plt.subplots(1, 1, figsize=(10, 10))
            self.logger.debug("Figura creada. Dibujando los datos en el mapa...")
            self.map_data.plot(ax=ax, column="coverage", cmap="coolwarm", legend=True)
            plt.title("Mapa de Cobertura")
            plt.xlabel("Longitud")
            plt.ylabel("Latitud")

            # Paso 2: Guardar la imagen
            image_path = "./coveragemap.png"
            self.logger.debug(f"Guardando la imagen del mapa en {image_path}...")
            plt.savefig(image_path)
            plt.close()
            self.logger.debug("Imagen guardada correctamente.")

            # Paso 3: Enviar la imagen a Matrix
            self.logger.debug("Leyendo la imagen del sistema para enviarla a Matrix...")
            with open(image_path, "rb") as f:
                self.logger.debug("Enviando la imagen como mensaje a la sala...")
                await self.send_matrix_message(
                    room_id, "Mapa de cobertura actualizado. Imagen generada."
                )
            self.logger.debug("Mapa enviado correctamente a Matrix.")

        except Exception as e:
            self.logger.error(f"Error durante la generación o envío del mapa: {e}")
    def export_map_as_html(self, output_path="./coveragemap.html"):
        """
        Genera un mapa interactivo con Folium utilizando los datos del plugin y lo guarda como HTML.
        
        Args:
            output_path (str): Ruta del archivo HTML donde se guardará el mapa.
        """
        # Depuración de la ruta recibida
        self.logger.debug(f"[EXPORT_MAP] output_path recibido: {output_path}")

        # Verificar si output_path no es una cadena
        if not isinstance(output_path, str):
            self.logger.error(f"[EXPORT_MAP_ERROR] output_path debe ser una cadena. Valor recibido: {output_path}")
            return

        self.logger.debug("Iniciando la generación del mapa interactivo.")
        self.logger.debug(f"Centro: {self.center_point}")
        self.logger.debug(f"Número de hexágonos: {len(self.map_data)}")

        # Crear el mapa interactivo
        m = folium.Map(location=[self.center_point[0], self.center_point[1]], zoom_start=12)

        # Dibujar hexágonos
        for _, row in self.map_data.iterrows():
            polygon = row["geometry"]
            color = "red" if row["coverage"] else "blue"
            folium.Polygon(
                locations=[(point[0], point[1]) for point in mapping(polygon)["coordinates"][0]],
                color=color,
                fill=True,
                fill_opacity=0.5
            ).add_to(m)

        # Añadir marcador en el centro
        folium.Marker(
            location=[self.center_point[0], self.center_point[1]],
            popup="Center Point",
            icon=folium.Icon(color="black")
        ).add_to(m)

        # Guardar el mapa
        self.logger.debug(f"Guardando el mapa interactivo en {output_path}")
        m.save(output_path)
        self.logger.debug("Mapa interactivo generado correctamente.")
