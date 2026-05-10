(function() {
    'use strict';

    // Show loading state
    document.getElementById('map').innerHTML =
        '<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#f5f5f5;"><p>Loading ancestor data...</p></div>';

    // Fetch data from API
    fetch('/api/ancestors/' + CURRENT_PERSON_ID)
        .then(function(r) { return r.json(); })
        .then(function(ANCESTORS) {
            document.getElementById('map').innerHTML = '';
            initMap(ANCESTORS);
        })
        .catch(function(err) {
            document.getElementById('map').innerHTML =
                '<div style="display:flex;align-items:center;justify-content:center;height:100%;"><p>Error loading data: ' + err.message + '</p></div>';
        });

    function initMap(ANCESTORS) {

    if (!ANCESTORS || ANCESTORS.length === 0) {
        document.getElementById('map').innerHTML =
            '<div style="display:flex;align-items:center;justify-content:center;height:100%;"><p>No locations found for your ancestors.</p></div>';
        return;
    }

    var map = L.map('map').setView([30, 0], 3);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18
    }).addTo(map);

    // Marker cluster group for performance
    var clusterGroup = L.markerClusterGroup({
        maxClusterRadius: 50,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        disableClusteringAtZoom: 10
    });
    map.addLayer(clusterGroup);

    var birthIcon = L.divIcon({
        className: 'custom-marker birth-marker',
        html: '<div style="width:12px;height:12px;background:#2d6a4f;border-radius:50%;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.3);"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });

    var deathIcon = L.divIcon({
        className: 'custom-marker death-marker',
        html: '<div style="width:12px;height:12px;background:#c0392b;border-radius:50%;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.3);"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });

    var allMarkers = [];
    var bounds = [];

    // Build ancestor lookup by ID for lineage reconstruction
    var ancestorById = {};
    ANCESTORS.forEach(function(a) { ancestorById[a.id] = a; });

    // Build child->parent mapping from generation order
    // For each ancestor at gen N, find ancestors at gen N+1 that could be their parents
    // Since we don't have explicit parent links, we'll show the generational chain

    function buildLineageLabels(generation, gender, side) {
        // Build the chain of relationship labels from You down to this generation
        var steps = [];
        steps.push({ name: 'You', rel: '' });
        for (var g = 1; g <= generation; g++) {
            var label;
            if (g === 1) {
                label = side === 'paternal' ? 'Father' : 'Mother';
            } else if (g === 2) {
                label = 'Grandfather / Grandmother';
            } else if (g === 3) {
                label = 'Great-Grandparent';
            } else {
                var n = g - 2;
                var suffix;
                if (11 <= n % 100 && n % 100 <= 13) suffix = 'th';
                else suffix = {1:'st',2:'nd',3:'rd'}[n%10] || 'th';
                label = n + suffix + ' Great-Grandparent';
            }
            steps.push({ name: '', rel: 'Gen ' + g + ': ' + label });
        }
        return steps;
    }

    function showLineagePanel(ancestorId) {
        var ancestor = ancestorById[ancestorId];
        if (!ancestor) return;

        var panel = document.getElementById('lineage-panel');
        var chain = document.getElementById('lineage-chain');
        var title = document.getElementById('lineage-title');

        title.textContent = 'Lineage to ' + ancestor.name;

        // For common ancestors view, fetch both paths from the API
        if (CURRENT_PERSON_ID === 'common') {
            chain.innerHTML = '<p style="padding:0.5rem;color:#666;">Loading lineage paths...</p>';
            panel.style.display = 'block';

            fetch('/api/lineage/' + ancestorId)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var keys = Object.keys(data);
                    var html = '<div class="lineage-side-by-side">';

                    for (var k = 0; k < keys.length; k++) {
                        var personId = keys[k];
                        var info = data[personId];

                        html += '<div class="lineage-column">';
                        html += '<div class="lineage-column-header">' + info.name + '</div>';

                        // "You" step
                        html += '<div class="lineage-step">';
                        html += '<div class="lineage-connector"><div class="lineage-dot"></div><div class="lineage-line"></div></div>';
                        html += '<div class="lineage-info"><span class="lineage-name">' + info.name.split(' ')[0] + '</span></div>';
                        html += '</div>';

                        for (var i = 0; i < info.path.length; i++) {
                            var step = info.path[i];
                            var isLast = (i === info.path.length - 1);

                            html += '<div class="lineage-step">';
                            html += '<div class="lineage-connector"><div class="lineage-dot' + (isLast ? ' active' : '') + '"></div>';
                            if (!isLast) html += '<div class="lineage-line"></div>';
                            html += '</div>';
                            html += '<div class="lineage-info">';
                            html += '<span class="lineage-name"><a href="' + step.familysearch_url + '" target="_blank">' + step.name + '</a></span>';
                            html += '<br><span class="lineage-rel">Gen ' + step.generation + '</span>';
                            html += '</div></div>';
                        }

                        html += '</div>'; // end column
                    }

                    html += '</div>'; // end side-by-side
                    chain.innerHTML = html;
                })
                .catch(function() {
                    chain.innerHTML = '<p style="padding:0.5rem;color:#c00;">Failed to load lineage.</p>';
                });
            return;
        }

        // Single-person view: trace path using child_id links
        var path = [];
        var current = ancestor;
        while (current) {
            path.unshift(current);
            if (current.child_id && ancestorById[current.child_id]) {
                current = ancestorById[current.child_id];
            } else {
                break;
            }
        }

        var html = '';

        // First step: You
        html += '<div class="lineage-step">';
        html += '<div class="lineage-connector"><div class="lineage-dot"></div><div class="lineage-line"></div></div>';
        html += '<div class="lineage-info"><span class="lineage-name">You</span></div>';
        html += '</div>';

        // If we have actual path with names (child_id links exist)
        if (path.length > 1 || (path.length === 1 && path[0].child_id === null)) {
            for (var i = 0; i < path.length; i++) {
                var step = path[i];
                var isLast = (i === path.length - 1);

                html += '<div class="lineage-step">';
                html += '<div class="lineage-connector"><div class="lineage-dot' + (isLast ? ' active' : '') + '"></div>';
                if (!isLast) html += '<div class="lineage-line"></div>';
                html += '</div>';
                html += '<div class="lineage-info">';
                html += '<span class="lineage-name"><a href="' + step.familysearch_url + '" target="_blank">' + step.name + '</a></span>';
                html += '<br><span class="lineage-rel">' + step.relationship + '</span>';
                if (isLast) {
                    if (step.birth && step.birth.date_original) {
                        html += '<br><span class="lineage-rel">b. ' + step.birth.date_original + '</span>';
                    }
                    if (step.death && step.death.date_original) {
                        html += '<br><span class="lineage-rel">d. ' + step.death.date_original + '</span>';
                    }
                }
                html += '</div></div>';
            }
        } else {
            // Fallback: show generation labels when child_id not available
            var generation = ancestor.generation;
            var side = ancestor.side;

            for (var g = 1; g < generation; g++) {
                var genLabel;
                if (g === 1) genLabel = (side === 'paternal' || side === 'common') ? 'Father' : 'Mother';
                else if (g === 2) genLabel = 'Grandparent';
                else if (g === 3) genLabel = 'Great-Grandparent';
                else {
                    var n = g - 2;
                    var suffix;
                    if (11 <= n % 100 && n % 100 <= 13) suffix = 'th';
                    else suffix = {1:'st',2:'nd',3:'rd'}[n%10] || 'th';
                    genLabel = n + suffix + ' Great-Grandparent';
                }

                html += '<div class="lineage-step">';
                html += '<div class="lineage-connector"><div class="lineage-dot"></div><div class="lineage-line"></div></div>';
                html += '<div class="lineage-info"><span class="lineage-rel">Gen ' + g + ': ' + genLabel + '</span></div>';
                html += '</div>';
            }

            // Final: clicked ancestor
            html += '<div class="lineage-step">';
            html += '<div class="lineage-connector"><div class="lineage-dot active"></div></div>';
            html += '<div class="lineage-info">';
            html += '<span class="lineage-name"><a href="' + ancestor.familysearch_url + '" target="_blank">' + ancestor.name + '</a></span>';
            html += '<br><span class="lineage-rel">' + ancestor.relationship + '</span>';
            if (ancestor.birth && ancestor.birth.date_original) {
                html += '<br><span class="lineage-rel">b. ' + ancestor.birth.date_original + '</span>';
            }
            if (ancestor.death && ancestor.death.date_original) {
                html += '<br><span class="lineage-rel">d. ' + ancestor.death.date_original + '</span>';
            }
            html += '</div></div>';
        }

        chain.innerHTML = html;
        panel.style.display = 'block';
    }

    // Build lookup: ancestor ID -> {birth: [lat, lng], death: [lat, lng]}
    var ancestorCoords = {};
    ANCESTORS.forEach(function(ancestor) {
        var coords = {};
        if (ancestor.birth && ancestor.birth.lat !== null && ancestor.birth.lng !== null) {
            coords.birth = [ancestor.birth.lat, ancestor.birth.lng];
        }
        if (ancestor.death && ancestor.death.lat !== null && ancestor.death.lng !== null) {
            coords.death = [ancestor.death.lat, ancestor.death.lng];
        }
        if (coords.birth || coords.death) {
            ancestorCoords[ancestor.id] = coords;
        }
    });

    // Track the active migration line
    var activeLine = null;
    var markerClicked = false;

    function clearActiveLine() {
        if (activeLine) {
            map.removeLayer(activeLine);
            activeLine = null;
        }
    }

    function drawMigrationLine(ancestorId, clickedType) {
        clearActiveLine();
        var coords = ancestorCoords[ancestorId];
        if (!coords || !coords.birth || !coords.death) return;

        // Draw dotted line from birth to death
        activeLine = L.polyline([coords.birth, coords.death], {
            color: '#555',
            weight: 2,
            dashArray: '6, 8',
            opacity: 0.8
        }).addTo(map);
    }

    ANCESTORS.forEach(function(ancestor) {
        if (ancestor.birth && ancestor.birth.lat !== null && ancestor.birth.lng !== null) {
            var marker = L.marker([ancestor.birth.lat, ancestor.birth.lng], { icon: birthIcon });
            marker.bindPopup(
                '<strong>' + ancestor.name + '</strong><br>' +
                '<em>' + ancestor.relationship + '</em><br>' +
                'Born: ' + (ancestor.birth.date_original || 'Unknown date') + '<br>' +
                ancestor.birth.place + '<br>' +
                '<a href="' + ancestor.familysearch_url + '" target="_blank">View on FamilySearch</a>'
            );
            marker._ancestorData = { type: 'birth', year: ancestor.birth.date_year, side: ancestor.side, id: ancestor.id };
            marker.on('click', function() {
                try {
                    markerClicked = true;
                    drawMigrationLine(ancestor.id, 'birth');
                    showLineagePanel(ancestor.id);
                } catch(e) {
                    console.error('Click handler error:', e);
                }
            });
            allMarkers.push(marker);
            bounds.push([ancestor.birth.lat, ancestor.birth.lng]);
        }

        if (ancestor.death && ancestor.death.lat !== null && ancestor.death.lng !== null) {
            var marker = L.marker([ancestor.death.lat, ancestor.death.lng], { icon: deathIcon });
            marker.bindPopup(
                '<strong>' + ancestor.name + '</strong><br>' +
                '<em>' + ancestor.relationship + '</em><br>' +
                'Died: ' + (ancestor.death.date_original || 'Unknown date') + '<br>' +
                ancestor.death.place + '<br>' +
                '<a href="' + ancestor.familysearch_url + '" target="_blank">View on FamilySearch</a>'
            );
            marker._ancestorData = { type: 'death', year: ancestor.death.date_year, side: ancestor.side, id: ancestor.id };
            marker.on('click', function() {
                try {
                    markerClicked = true;
                    drawMigrationLine(ancestor.id, 'death');
                    showLineagePanel(ancestor.id);
                } catch(e) {
                    console.error('Click handler error:', e);
                }
            });
            allMarkers.push(marker);
            bounds.push([ancestor.death.lat, ancestor.death.lng]);
        }
    });

    // Clear line when clicking on the map background (not a marker)
    map.on('click', function(e) {
        if (markerClicked) {
            markerClicked = false;
            return;
        }
        clearActiveLine();
        document.getElementById('lineage-panel').style.display = 'none';
    });

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [30, 30] });
    }

    // Add all markers to cluster group initially
    clusterGroup.addLayers(allMarkers);

    document.getElementById('ancestor-count').textContent = ANCESTORS.length + ' ancestors';

    var years = [];
    ANCESTORS.forEach(function(a) {
        if (a.birth && a.birth.date_year) years.push(a.birth.date_year);
        if (a.death && a.death.date_year) years.push(a.death.date_year);
    });

    if (years.length === 0) {
        document.getElementById('timeline').style.display = 'none';
        document.getElementById('map').style.bottom = '0';
        return;
    }

    var minYear = years.reduce(function(a, b) { return a < b ? a : b; });
    var maxYear = years.reduce(function(a, b) { return a > b ? a : b; });

    var slider = document.getElementById('slider');
    noUiSlider.create(slider, {
        start: [minYear, maxYear],
        connect: true,
        range: { min: minYear, max: maxYear },
        step: 1,
        tooltips: false
    });

    document.getElementById('range-start').textContent = minYear;
    document.getElementById('range-end').textContent = maxYear;

    // Filter controls
    var showUnknownCheckbox = document.getElementById('show-unknown');
    var showPaternalCheckbox = document.getElementById('show-paternal');
    var showMaternalCheckbox = document.getElementById('show-maternal');

    function filterMarkers() {
        var values = slider.noUiSlider.get();
        var rangeStart = Math.round(parseFloat(values[0]));
        var rangeEnd = Math.round(parseFloat(values[1]));
        var showUnknown = showUnknownCheckbox.checked;
        var showPaternal = showPaternalCheckbox.checked;
        var showMaternal = showMaternalCheckbox.checked;

        document.getElementById('range-start').textContent = rangeStart;
        document.getElementById('range-end').textContent = rangeEnd;

        var toAdd = [];
        var toRemove = [];

        allMarkers.forEach(function(marker) {
            var data = marker._ancestorData;
            var year = data.year;
            var side = data.side;
            var visible = false;

            // Side filter
            var sideVisible = true;
            if (side === 'paternal' && !showPaternal) { sideVisible = false; }
            else if (side === 'maternal' && !showMaternal) { sideVisible = false; }

            // Date filter
            if (!sideVisible) {
                visible = false;
            } else if (year === null || year === undefined) {
                visible = showUnknown;
            } else {
                visible = year >= rangeStart && year <= rangeEnd;
            }

            if (visible) {
                if (!clusterGroup.hasLayer(marker)) toAdd.push(marker);
            } else {
                if (clusterGroup.hasLayer(marker)) toRemove.push(marker);
            }
        });

        // Batch operations for performance
        if (toRemove.length > 0) clusterGroup.removeLayers(toRemove);
        if (toAdd.length > 0) clusterGroup.addLayers(toAdd);

        var visibleCount = 0;
        allMarkers.forEach(function(m) {
            if (clusterGroup.hasLayer(m)) visibleCount++;
        });
        document.getElementById('ancestor-count').textContent =
            Math.round(visibleCount / 2) + ' ancestors visible (of ' + ANCESTORS.length + ')';
    }

    // Debounce slider updates for smoother performance
    var filterTimeout = null;

    function debouncedFilter() {
        if (filterTimeout) clearTimeout(filterTimeout);
        filterTimeout = setTimeout(filterMarkers, 50);
    }

    slider.noUiSlider.on('update', debouncedFilter);
    showUnknownCheckbox.addEventListener('change', filterMarkers);
    showPaternalCheckbox.addEventListener('change', filterMarkers);
    showMaternalCheckbox.addEventListener('change', filterMarkers);

    // Scrape status polling on the map page
    var scrapeBar = document.getElementById('scrape-bar');
    function pollScrapeStatus() {
        fetch('/api/scrape-status')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var personId = typeof CURRENT_PERSON_ID !== 'undefined' ? CURRENT_PERSON_ID : '';
                var relevant = [];
                var anyRunning = false;

                for (var key in data) {
                    if (key.startsWith(personId + '_') || !personId) {
                        relevant.push({ key: key, info: data[key] });
                        if (data[key].status === 'running') anyRunning = true;
                    }
                }

                if (anyRunning) {
                    var parts = relevant.map(function(r) {
                        var side = r.key.split('_')[1];
                        var icon = r.info.status === 'running' ? '⏳' : '✓';
                        return icon + ' ' + side + ': ' + r.info.count + ' ancestors';
                    });
                    scrapeBar.innerHTML = 'Scraping in progress — ' + parts.join(' | ') +
                        ' <span style="font-size:0.75rem;opacity:0.7;">(refresh page to see new data)</span>';
                    scrapeBar.style.display = 'block';
                    setTimeout(pollScrapeStatus, 5000);
                } else {
                    scrapeBar.style.display = 'none';
                }
            })
            .catch(function() { setTimeout(pollScrapeStatus, 10000); });
    }
    pollScrapeStatus();

    // Search functionality
    var searchInput = document.getElementById('search-input');
    var searchResults = document.getElementById('search-results');
    var searchTimeout = null;

    // Build marker lookup by ancestor ID for zooming
    var markersByAncestorId = {};
    allMarkers.forEach(function(m) {
        var id = m._ancestorData.id;
        if (!markersByAncestorId[id]) markersByAncestorId[id] = [];
        markersByAncestorId[id].push(m);
    });

    searchInput.addEventListener('input', function() {
        if (searchTimeout) clearTimeout(searchTimeout);
        var query = searchInput.value.trim().toLowerCase();

        if (query.length < 2) {
            searchResults.style.display = 'none';
            return;
        }

        searchTimeout = setTimeout(function() {
            var matches = [];
            for (var i = 0; i < ANCESTORS.length && matches.length < 15; i++) {
                var a = ANCESTORS[i];
                if (a.name.toLowerCase().indexOf(query) !== -1) {
                    matches.push(a);
                }
            }

            if (matches.length === 0) {
                searchResults.innerHTML = '<div class="search-result-item"><span class="search-result-detail">No results</span></div>';
                searchResults.style.display = 'block';
                return;
            }

            var html = '';
            matches.forEach(function(a) {
                var birthInfo = a.birth && a.birth.date_original ? 'b. ' + a.birth.date_original : '';
                var placeInfo = a.birth && a.birth.place ? a.birth.place : '';
                var rel = (a.relationship || '').replace(/<br>/g, ' / ').replace(/<[^>]*>/g, '');
                var detail = [rel, birthInfo, placeInfo].filter(Boolean).join(' · ');

                html += '<div class="search-result-item" data-id="' + a.id + '">';
                html += '<div class="search-result-name">' + a.name + '</div>';
                html += '<div class="search-result-detail">' + detail + '</div>';
                html += '</div>';
            });

            searchResults.innerHTML = html;
            searchResults.style.display = 'block';

            // Add click handlers
            var items = searchResults.querySelectorAll('.search-result-item');
            items.forEach(function(item) {
                item.addEventListener('click', function() {
                    var ancestorId = item.getAttribute('data-id');
                    var ancestor = ancestorById[ancestorId];
                    if (!ancestor) return;

                    // Zoom to ancestor's location
                    var lat = null, lng = null;
                    if (ancestor.birth && ancestor.birth.lat) {
                        lat = ancestor.birth.lat;
                        lng = ancestor.birth.lng;
                    } else if (ancestor.death && ancestor.death.lat) {
                        lat = ancestor.death.lat;
                        lng = ancestor.death.lng;
                    }

                    if (lat && lng) {
                        map.setView([lat, lng], 10);
                    }

                    // Open popup on the marker
                    var markers = markersByAncestorId[ancestorId];
                    if (markers && markers.length > 0) {
                        // Spiderfy cluster if needed, then open popup
                        clusterGroup.zoomToShowLayer(markers[0], function() {
                            markers[0].openPopup();
                        });
                    }

                    // Show lineage and migration line
                    drawMigrationLine(ancestorId, 'birth');
                    showLineagePanel(ancestorId);

                    // Close search
                    searchResults.style.display = 'none';
                    searchInput.value = ancestor.name;
                });
            });
        }, 150);
    });

    // Close search results when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
            searchResults.style.display = 'none';
        }
    });

    // Re-show results on focus if there's text
    searchInput.addEventListener('focus', function() {
        if (searchInput.value.trim().length >= 2 && searchResults.innerHTML) {
            searchResults.style.display = 'block';
        }
    });

    } // end initMap
})();
