// Leaflet JS minimal pour cartes et GeoJSON
(function() {
    'use strict';

    // Namespace global
    var L = {};

    // Utilitaires de base
    L.Util = {
        extend: function(dest) {
            for (var i = 1; i < arguments.length; i++) {
                var src = arguments[i];
                for (var k in src) {
                    dest[k] = src[k];
                }
            }
            return dest;
        },

        create: function(tagName, className, container) {
            var el = document.createElement(tagName);
            if (className) el.className = className;
            if (container) container.appendChild(el);
            return el;
        },

        setOptions: function(obj, options) {
            obj.options = L.Util.extend({}, obj.options, options);
            return obj.options;
        }
    };

    // Classe de base
    L.Class = function() {};
    L.Class.extend = function(props) {
        var NewClass = function() {
            if (this.initialize) {
                this.initialize.apply(this, arguments);
            }
        };

        NewClass.prototype = Object.create(this.prototype);
        L.Util.extend(NewClass.prototype, props);

        NewClass.extend = L.Class.extend;
        NewClass.include = function(props) {
            L.Util.extend(this.prototype, props);
        };

        return NewClass;
    };

    // Gestionnaire d'événements
    L.Evented = L.Class.extend({
        on: function(types, fn, context) {
            var events = this._events = this._events || {};
            types = types.split(' ');
            for (var i = 0; i < types.length; i++) {
                var type = types[i];
                events[type] = events[type] || [];
                events[type].push({fn: fn, ctx: context || this});
            }
            return this;
        },

        fire: function(type, data) {
            var events = this._events && this._events[type];
            if (events) {
                for (var i = 0; i < events.length; i++) {
                    events[i].fn.call(events[i].ctx, data);
                }
            }
            return this;
        }
    });

    // Coordonnées
    L.LatLng = function(lat, lng) {
        this.lat = +lat;
        this.lng = +lng;
    };

    L.latLng = function(lat, lng) {
        return new L.LatLng(lat, lng);
    };

    // Bounds
    L.LatLngBounds = function(southWest, northEast) {
        this._southWest = L.latLng(southWest);
        this._northEast = L.latLng(northEast);
    };

    L.latLngBounds = function(southWest, northEast) {
        return new L.LatLngBounds(southWest, northEast);
    };

    // Point
    L.Point = function(x, y) {
        this.x = +x;
        this.y = +y;
    };

    L.point = function(x, y) {
        return new L.Point(x, y);
    };

    // Transformation de coordonnées
    L.CRS = {
        latLngToPoint: function(latlng, zoom) {
            var lat = latlng.lat;
            var lng = latlng.lng;
            var x = (lng + 180) / 360 * Math.pow(2, zoom);
            var y = (1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, zoom);
            return L.point(x, y);
        },

        pointToLatLng: function(point, zoom) {
            var x = point.x / Math.pow(2, zoom) * 360 - 180;
            var y = 2 * (Math.atan(Math.exp((1 - point.y / Math.pow(2, zoom) * 2) * Math.PI)) - Math.PI / 4) * 180 / Math.PI;
            return L.latLng(y, x);
        }
    };

    // Layer de base
    L.Layer = L.Evented.extend({
        addTo: function(map) {
            map.addLayer(this);
            return this;
        },

        remove: function() {
            if (this._map) {
                this._map.removeLayer(this);
            }
            return this;
        }
    });

    // GridLayer (tuiles)
    L.GridLayer = L.Layer.extend({
        options: {
            tileSize: 256,
            opacity: 1,
            updateWhenIdle: false,
            updateInterval: 200
        },

        initialize: function(options) {
            L.Util.setOptions(this, options);
        },

        onAdd: function(map) {
            this._map = map;
            this._container = L.Util.create('div', 'leaflet-layer', map._container);
            this._container.style.zIndex = 1;
            this._update();
        },

        onRemove: function(map) {
            if (this._container) {
                map._container.removeChild(this._container);
            }
            this._map = null;
        },

        _update: function() {
            if (!this._map) return;

            var map = this._map;
            var zoom = map._zoom;
            var bounds = map.getBounds();
            var tileSize = this.options.tileSize;

            // Calcul des tuiles nécessaires
            var nw = L.CRS.latLngToPoint(bounds._northEast, zoom);
            var se = L.CRS.latLngToPoint(bounds._southWest, zoom);

            var tileBounds = {
                x: Math.floor(nw.x / tileSize),
                y: Math.floor(nw.y / tileSize),
                maxX: Math.floor(se.x / tileSize),
                maxY: Math.floor(se.y / tileSize)
            };

            // Créer les tuiles
            for (var x = tileBounds.x; x <= tileBounds.maxX; x++) {
                for (var y = tileBounds.y; y <= tileBounds.maxY; y++) {
                    this._addTile(x, y, zoom);
                }
            }
        },

        _addTile: function(x, y, z) {
            var tileId = x + '_' + y + '_' + z;
            if (this._tiles && this._tiles[tileId]) return;

            var tile = L.Util.create('img', 'leaflet-tile', this._container);
            tile.src = this._getTileUrl(x, y, z);
            tile.style.width = this.options.tileSize + 'px';
            tile.style.height = this.options.tileSize + 'px';

            var pos = L.point(x * this.options.tileSize, y * this.options.tileSize);
            tile.style.transform = 'translate(' + pos.x + 'px, ' + pos.y + 'px)';

            if (!this._tiles) this._tiles = {};
            this._tiles[tileId] = tile;
        }
    });

    // TileLayer
    L.TileLayer = L.GridLayer.extend({
        options: {
            subdomains: 'abc',
            errorTileUrl: '',
            zoomOffset: 0,
            maxZoom: 18,
            minZoom: 0,
            tms: false,
            zoomReverse: false,
            detectRetina: false,
            attribution: ''
        },

        initialize: function(url, options) {
            this._url = url;
            L.GridLayer.prototype.initialize.call(this, options);
        },

        _getTileUrl: function(x, y, z) {
            return this._url
                .replace('{s}', this.options.subdomains.charAt(Math.abs(x + y) % this.options.subdomains.length))
                .replace('{x}', x)
                .replace('{y}', y)
                .replace('{z}', z);
        }
    });

    L.tileLayer = function(url, options) {
        return new L.TileLayer(url, options);
    };

    // GeoJSON Layer
    L.GeoJSON = L.Layer.extend({
        initialize: function(geojson, options) {
            this._geojson = geojson;
            L.Util.setOptions(this, options);
        },

        onAdd: function(map) {
            this._map = map;
            this._container = L.Util.create('div', 'leaflet-geojson-layer', map._container);
            this._render();
        },

        onRemove: function(map) {
            if (this._container) {
                map._container.removeChild(this._container);
            }
            this._map = null;
        },

        _render: function() {
            if (!this._geojson || !this._geojson.features) return;

            this._geojson.features.forEach(function(feature) {
                this._renderFeature(feature);
            }, this);
        },

        _renderFeature: function(feature) {
            var geometry = feature.geometry;
            if (!geometry) return;

            switch (geometry.type) {
                case 'Point':
                    this._renderPoint(geometry.coordinates, feature);
                    break;
                case 'LineString':
                    this._renderLineString(geometry.coordinates, feature);
                    break;
                case 'Polygon':
                    this._renderPolygon(geometry.coordinates, feature);
                    break;
            }
        },

        _renderPoint: function(coords, feature) {
            var el = L.Util.create('div', 'leaflet-geojson-point', this._container);
            el.style.position = 'absolute';
            el.style.width = '8px';
            el.style.height = '8px';
            el.style.borderRadius = '50%';
            el.style.backgroundColor = this.options.fillColor || '#3388ff';
            el.style.border = '2px solid ' + (this.options.color || '#3388ff');

            var latlng = L.latLng(coords[1], coords[0]);
            var point = this._map.latLngToContainerPoint(latlng);
            el.style.left = (point.x - 4) + 'px';
            el.style.top = (point.y - 4) + 'px';

            if (this.options.onEachFeature) {
                this.options.onEachFeature(feature, {bindPopup: function(content) {
                    el.onclick = function() { alert(content); };
                }});
            }
        },

        _renderLineString: function(coords, feature) {
            var el = L.Util.create('svg', 'leaflet-geojson-linestring', this._container);
            el.style.position = 'absolute';
            el.style.width = '100%';
            el.style.height = '100%';
            el.style.pointerEvents = 'none';

            var path = 'M';
            coords.forEach(function(coord, i) {
                var latlng = L.latLng(coord[1], coord[0]);
                var point = this._map.latLngToContainerPoint(latlng);
                path += (i === 0 ? '' : 'L') + point.x + ',' + point.y;
            }, this);

            var pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            pathEl.setAttribute('d', path);
            pathEl.setAttribute('stroke', this.options.color || '#3388ff');
            pathEl.setAttribute('stroke-width', this.options.weight || 2);
            pathEl.setAttribute('fill', 'none');
            pathEl.setAttribute('opacity', this.options.opacity || 1);

            el.appendChild(pathEl);
        },

        _renderPolygon: function(coords, feature) {
            // Pour les polygones, traiter comme LineString fermé
            coords[0].push(coords[0][0]); // Fermer le polygone
            this._renderLineString(coords[0], feature);
        }
    });

    L.geoJSON = function(geojson, options) {
        return new L.GeoJSON(geojson, options);
    };

    // LayerGroup
    L.LayerGroup = L.Layer.extend({
        initialize: function(layers) {
            this._layers = {};
            if (layers) {
                for (var i = 0; i < layers.length; i++) {
                    this.addLayer(layers[i]);
                }
            }
        },

        addLayer: function(layer) {
            var id = this._leaflet_id = this._leaflet_id || ++L.LayerGroup._layerId;
            this._layers[id] = layer;
            if (this._map) {
                this._map.addLayer(layer);
            }
            return this;
        },

        removeLayer: function(layer) {
            var id = layer._leaflet_id || layer;
            if (this._layers[id]) {
                if (this._map) {
                    this._map.removeLayer(this._layers[id]);
                }
                delete this._layers[id];
            }
            return this;
        }
    });

    L.layerGroup = function(layers) {
        return new L.LayerGroup(layers);
    };

    L.LayerGroup._layerId = 0;

    // Marker
    L.Marker = L.Layer.extend({
        options: {
            icon: {
                iconUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEyIDJDOC4xMyAyIDUgNS4xMyA1IDhDOC41IDE0LjY3IDEwLjUgMTggMTIgMTJDMTMuNSAxOCA5LjUgMTQuNjcgOSA4QzkgNS4xMyAxMi4xMyAyIDEyIDJaTTEyIDEzQzEwLjc2IDEzIDEwIDEyLjI0IDEwIDExQzEwIDEwLjc2IDEwLjc2IDEwIDExIDEwQzEyLjI0IDEwIDEzIDEwLjc2IDEzIDExQzEzIDEyLjI0IDEyLjI0IDEzIDEyIDEzWiIgZmlsbD0iI2VmNDQ0NCIvPgo8L3N2Zz4K',
                iconSize: [24, 24],
                iconAnchor: [12, 24],
                popupAnchor: [0, -24]
            }
        },

        initialize: function(latlng, options) {
            L.Util.setOptions(this, options);
            this._latlng = L.latLng(latlng);
        },

        onAdd: function(map) {
            this._map = map;
            this._container = L.Util.create('img', 'leaflet-marker-icon', map._container);
            this._container.src = this.options.icon.iconUrl;
            this._container.style.position = 'absolute';
            this._container.style.width = this.options.icon.iconSize[0] + 'px';
            this._container.style.height = this.options.icon.iconSize[1] + 'px';
            this._container.style.cursor = 'pointer';
            this._update();

            // Appliquer la popup en attente si elle existe
            if (this._pendingPopup) {
                this._container.onclick = () => {
                    alert(this._pendingPopup);
                };
                this._pendingPopup = null;
            }
        },

        onRemove: function(map) {
            if (this._container) {
                map._container.removeChild(this._container);
            }
            this._map = null;
        },

        _update: function() {
            if (!this._map) return;

            var pos = this._map.latLngToContainerPoint(this._latlng);
            this._container.style.left = (pos.x - this.options.icon.iconAnchor[0]) + 'px';
            this._container.style.top = (pos.y - this.options.icon.iconAnchor[1]) + 'px';
        },

        bindPopup: function(content) {
            this._popupContent = content;
            if (this._container) {
                this._container.onclick = () => {
                    alert(content);
                };
            } else {
                // Stocker pour plus tard si le container n'existe pas encore
                this._pendingPopup = content;
            }
            return this;
        },

        openPopup: function() {
            if (this._popupContent) {
                alert(this._popupContent);
            }
            return this;
        }
    });

    L.marker = function(latlng, options) {
        return new L.Marker(latlng, options);
    };

    // FeatureGroup (pour getBounds)
    L.FeatureGroup = L.LayerGroup.extend({
        getBounds: function() {
            var bounds = new L.LatLngBounds();
            this.eachLayer(function(layer) {
                if (layer.getBounds) {
                    bounds.extend(layer.getBounds());
                }
            });
            return bounds;
        }
    });

    L.featureGroup = function(layers) {
        return new L.FeatureGroup(layers);
    };

    // Map principale
    L.Map = L.Evented.extend({
        options: {
            center: [0, 0],
            zoom: 0,
            zoomControl: true
        },

        initialize: function(id, options) {
            L.Util.setOptions(this, options);
            this._container = document.getElementById(id);
            this._initContainer();
            this.setView(this.options.center, this.options.zoom);
        },

        _initContainer: function() {
            this._container.className += ' leaflet-container';
            this._container.style.position = 'relative';
            this._container.style.overflow = 'hidden';

            this._layers = [];
            this._controls = [];
        },

        setView: function(center, zoom) {
            this._center = L.latLng(center);
            this._zoom = zoom;
            this._update();
            return this;
        },

        getCenter: function() {
            return this._center;
        },

        getZoom: function() {
            return this._zoom;
        },

        getBounds: function() {
            var center = this._center;
            var zoom = this._zoom;

            // Approximation des bounds
            var latDiff = 180 / Math.pow(2, zoom);
            var lngDiff = 360 / Math.pow(2, zoom);

            return L.latLngBounds(
                [center.lat - latDiff/2, center.lng - lngDiff/2],
                [center.lat + latDiff/2, center.lng + lngDiff/2]
            );
        },

        latLngToContainerPoint: function(latlng) {
            var center = this._center;
            var zoom = this._zoom;

            var centerPoint = L.CRS.latLngToPoint(center, zoom);
            var targetPoint = L.CRS.latLngToPoint(latlng, zoom);

            var containerCenter = L.point(this._container.offsetWidth / 2, this._container.offsetHeight / 2);

            return L.point(
                containerCenter.x + (targetPoint.x - centerPoint.x) * 256,
                containerCenter.y + (targetPoint.y - centerPoint.y) * 256
            );
        },

        fitBounds: function(bounds) {
            if (!bounds.isValid()) return this;

            var center = bounds.getCenter();
            var zoom = this._getBoundsZoom(bounds);
            return this.setView(center, zoom);
        },

        _getBoundsZoom: function(bounds) {
            var containerSize = L.point(this._container.offsetWidth, this._container.offsetHeight);
            var boundsSize = L.point(
                Math.abs(bounds._northEast.lng - bounds._southWest.lng),
                Math.abs(bounds._northEast.lat - bounds._southWest.lat)
            );

            var zoom = 0;
            while (zoom < 18) {
                var scale = Math.pow(2, zoom);
                if (boundsSize.x * scale < containerSize.x && boundsSize.y * scale < containerSize.y) {
                    break;
                }
                zoom++;
            }
            return zoom;
        },

        addLayer: function(layer) {
            this._layers.push(layer);
            if (layer.onAdd) {
                layer.onAdd(this);
            }
            this._update();
            return this;
        },

        removeLayer: function(layer) {
            var index = this._layers.indexOf(layer);
            if (index !== -1) {
                this._layers.splice(index, 1);
                if (layer.onRemove) {
                    layer.onRemove(this);
                }
            }
            return this;
        },

        hasLayer: function(layer) {
            return this._layers.indexOf(layer) !== -1;
        },

        eachLayer: function(fn, context) {
            for (var i = 0; i < this._layers.length; i++) {
                fn.call(context, this._layers[i]);
            }
        },

        invalidateSize: function() {
            // Force le recalcul des dimensions et met à jour les couches
            this._update();
            return this;
        },

        _update: function() {
            for (var i = 0; i < this._layers.length; i++) {
                var layer = this._layers[i];
                if (layer._update) {
                    layer._update();
                }
            }
        }
    });

    // Fonctions d'aide
    L.map = function(id, options) {
        return new L.Map(id, options);
    };

    // Fonction globale
    window.L = L;

})();