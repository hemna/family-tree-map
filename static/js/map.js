(function() {
    'use strict';

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
            marker._ancestorData = { type: 'birth', year: ancestor.birth.date_year };
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
            marker._ancestorData = { type: 'death', year: ancestor.death.date_year };
            allMarkers.push(marker);
            bounds.push([ancestor.death.lat, ancestor.death.lng]);
        }
    });

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [30, 30] });
    }

    allMarkers.forEach(function(m) { m.addTo(map); });

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

    var minYear = Math.min.apply(null, years);
    var maxYear = Math.max.apply(null, years);

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

    var showUnknownCheckbox = document.getElementById('show-unknown');

    function filterMarkers() {
        var values = slider.noUiSlider.get();
        var rangeStart = Math.round(parseFloat(values[0]));
        var rangeEnd = Math.round(parseFloat(values[1]));
        var showUnknown = showUnknownCheckbox.checked;

        document.getElementById('range-start').textContent = rangeStart;
        document.getElementById('range-end').textContent = rangeEnd;

        allMarkers.forEach(function(marker) {
            var year = marker._ancestorData.year;
            var visible = false;

            if (year === null || year === undefined) {
                visible = showUnknown;
            } else {
                visible = year >= rangeStart && year <= rangeEnd;
            }

            if (visible) {
                if (!map.hasLayer(marker)) marker.addTo(map);
            } else {
                if (map.hasLayer(marker)) map.removeLayer(marker);
            }
        });
    }

    slider.noUiSlider.on('update', filterMarkers);
    showUnknownCheckbox.addEventListener('change', filterMarkers);
})();
