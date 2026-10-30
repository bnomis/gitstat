(function () {
  'use strict';

  var data = JSON.parse(document.getElementById('wambatic-data').textContent);
  var root = document.documentElement;
  var dark = window.matchMedia('(prefers-color-scheme: dark)');
  var config = { responsive: true, displaylogo: false };
  var periodKeys = [];
  var shown = data.initial;

  Object.keys(data.periods).forEach(function (granularity) {
    data.periods[granularity].forEach(function (figure) {
      if (periodKeys.indexOf(figure.key) < 0) {
        periodKeys.push(figure.key);
      }
    });
  });

  function activeTheme() {
    var set = root.getAttribute('data-theme');
    if (set === 'light' || set === 'dark') {
      return set;
    }
    return dark.matches ? 'dark' : 'light';
  }

  function copy(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function gradient(steps) {
    return steps.map(function (colour, index) {
      return [index / (steps.length - 1), colour];
    });
  }

  function colourTrace(trace, colours) {
    var meta = trace.meta || {};
    if (meta.slot) {
      var colour = colours.categorical[meta.slot - 1];
      trace.marker = trace.marker || {};
      trace.marker.color = colour;
      if (trace.type === 'bar') {
        trace.marker.pattern = trace.marker.pattern || {};
        trace.marker.pattern.fgcolor = colour;
      } else {
        trace.line = trace.line || {};
        trace.line.color = colour;
      }
    }
    if (meta.scale === 'sequential') {
      trace.colorscale = gradient(colours.sequential);
    }
  }

  function themed(figure, theme) {
    var colours = data.palette[theme];
    var result = copy(figure);
    var layout = result.layout;
    result.data.forEach(function (trace) {
      colourTrace(trace, colours);
    });
    layout.paper_bgcolor = colours.surface;
    layout.plot_bgcolor = colours.surface;
    layout.font = layout.font || {};
    layout.font.color = colours.ink;
    ['xaxis', 'yaxis'].forEach(function (name) {
      layout[name] = layout[name] || {};
      layout[name].gridcolor = colours.grid;
      layout[name].zerolinecolor = colours.ink_secondary;
    });
    (layout.annotations || []).forEach(function (annotation) {
      if (annotation.name === 'caption') {
        annotation.font = annotation.font || {};
        annotation.font.color = colours.ink_secondary;
      }
    });
    return result;
  }

  function draw(figure, redraw) {
    var element = document.getElementById(figure.key);
    if (!element) {
      return;
    }
    var ready = themed(figure, activeTheme());
    if (redraw) {
      Plotly.react(element, ready.data, ready.layout, config);
    } else {
      Plotly.newPlot(element, ready.data, ready.layout, config);
    }
  }

  function drawPeriods(granularity, redraw) {
    var figures = {};
    data.periods[granularity].forEach(function (figure) {
      figures[figure.key] = figure;
    });
    periodKeys.forEach(function (key) {
      var element = document.getElementById(key);
      if (!element) {
        return;
      }
      if (figures[key]) {
        element.parentElement.hidden = false;
        draw(figures[key], redraw);
      } else {
        element.parentElement.hidden = true;
      }
    });
  }

  function drawFixed(redraw) {
    data.range.forEach(function (figure) {
      draw(figure, redraw);
    });
    if (data.calendar) {
      draw(data.calendar, redraw);
    }
  }

  function showTables(granularity) {
    document.querySelectorAll('table.period').forEach(function (table) {
      table.hidden = table.getAttribute('data-granularity') !== granularity;
    });
  }

  function choose(event) {
    shown = event.target.value;
    showTables(shown);
    drawPeriods(shown, true);
  }

  document.querySelectorAll('input[name="granularity"]').forEach(function (radio) {
    radio.addEventListener('change', choose);
  });

  dark.addEventListener('change', function () {
    drawPeriods(shown, true);
    drawFixed(true);
  });

  showTables(shown);
  drawPeriods(shown, false);
  drawFixed(false);
})();
