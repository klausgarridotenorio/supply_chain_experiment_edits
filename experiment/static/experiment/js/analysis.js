// Decision Support System elements
const analysisRP = document.getElementById('analysisRP');
const analysisPrice = document.getElementById('analysisPrice');
const analysisQuantity = document.getElementById('analysisQuantity');
const btnDisplayProfits = document.getElementById('btn-display-profits');
let profitLineChart = null;

// The hypothetical Retail Price chosen in the dropdown (4 or 5, default 4).
// The DSS never uses the true P draw -- only this user-chosen value.
function selectedRetailPrice() {
  return parseInt(analysisRP && analysisRP.value) || 4;
}

document.addEventListener('DOMContentLoaded', () => {
  initializeDecisionSupport();
});

////////////////////////////////////////////////////////////////////////////////
// Decision Support System
////////////////////////////////////////////////////////////////////////////////
function initializeDecisionSupport() {
  // Add event listeners for analysis inputs
  if (analysisRP && analysisPrice && analysisQuantity && btnDisplayProfits) {
    analysisPrice.addEventListener('input', onAnalysisInputChanged);
    analysisQuantity.addEventListener('input', onAnalysisInputChanged);
    analysisRP.addEventListener('change', onAnalysisInputChanged);

    // Ensure button starts disabled
    btnDisplayProfits.disabled = true;
  } else {
    console.warn('DSS elements not found:', {
      analysisRP: !!analysisRP,
      analysisPrice: !!analysisPrice,
      analysisQuantity: !!analysisQuantity,
      btnDisplayProfits: !!btnDisplayProfits
    });
  }
}

function onAnalysisInputChanged() {
  updateDisplayProfitsButton();
  // Dynamic recalculation: as soon as the inputs are valid, redraw the
  // graph and the profit split for the currently selected P.
  if (!btnDisplayProfits.disabled) {
    plotProfitsVsDemand();
  }
}

// "TEST offer" button in the interface table: copy the counterpart's
// standing proposal into the DSS inputs and plot it immediately, so the
// impact of the deal on the table can be inspected before CONFIRM. The
// hypothetical P stays whatever is selected in the dropdown.
function testOffer() {
  const proposal = document.getElementById('otherProposal');
  if (!proposal) {
    return;
  }
  // Same parsing as sendAccept (experiment.js): "€ <price><br><quantity>".
  const parts = proposal.innerHTML.split('<br>');
  const price = parseFloat(parts[0].replace('€', ''));
  const quantity = parseInt(parts[1]);
  if (isNaN(price) || isNaN(quantity)) {
    return;
  }
  analysisPrice.value = price;
  analysisQuantity.value = quantity;
  onAnalysisInputChanged();
}

function updateDisplayProfitsButton() {
  if (analysisPrice && analysisQuantity && btnDisplayProfits) {
    const priceValue = parseFloat(analysisPrice.value);
    const quantityValue = parseInt(analysisQuantity.value);

    if (!isNaN(priceValue) && !isNaN(quantityValue) && priceValue > 0 && quantityValue > 0) {
      btnDisplayProfits.disabled = false;
      btnDisplayProfits.style.backgroundColor = '#007bff';
      btnDisplayProfits.style.cursor = 'pointer';
    } else {
      btnDisplayProfits.disabled = true;
      btnDisplayProfits.style.backgroundColor = '#6c757d';
      btnDisplayProfits.style.cursor = 'not-allowed';
    }
  }
}

// Expected demand calculation based on quantity - same formula as before
function expectedDemandFromQuantity(quantity) {
  const demandMin = js_vars.demand_min || 0;
  const demandMax = js_vars.demand_max || 100;

  const numerator = ((quantity * quantity - demandMin * demandMin) / 2 + quantity * (demandMax - quantity));
  const denominator = (demandMax - demandMin);
  const demand = numerator / denominator;

  return Math.max(0, Math.min(demandMax, demand));
}

// Build profit data series for line chart
function buildProfitSeries(graph_price, graph_quantity) {
  const p = parseFloat(graph_price);
  const q = parseInt(graph_quantity);
  // The P comes from the dropdown (hypothetical 4 or 5), NOT from the
  // true draw -- the DSS shows conditional what-if analysis only.
  const marketPrice = selectedRetailPrice();
  const productionCost = js_vars.production_cost || 4;
  const demandMin = js_vars.demand_min || 0;
  const demandMax = js_vars.demand_max || 100;

  const demandAxis = [];
  const supplierProfits = [];
  const retailerProfits = [];

  // Generate profit data for each demand level
  for (let d = demandMin; d <= demandMax; d++) {
    const expectedSales = Math.min(q, d);

    // Correct profit formulas
    const supplierProfit = (p * expectedSales) - (productionCost * q);
    const retailerProfit = (marketPrice - p) * expectedSales;

    demandAxis.push(d);
    supplierProfits.push(supplierProfit);
    retailerProfits.push(retailerProfit);
  }

  // Calculate expected profits at expected demand point
  const expectedDemand = expectedDemandFromQuantity(q);
  const expectedSales = Math.min(q, expectedDemand);
  const expectedSupplierProfit = (p * expectedSales) - (productionCost * q);
  const expectedRetailerProfit = (marketPrice - p) * expectedSales;

  return {
    demandAxis,
    supplierProfits,
    retailerProfits: retailerProfits,
    expectedDemand,
    expectedSupplierProfit,
    expectedRetailerProfit: expectedRetailerProfit
  };
}

// Main function called by the button - make it global
function plotProfitsVsDemand() {
  console.log('plotProfitsVsDemand called');

  if (!analysisPrice || !analysisQuantity) {
    alert('Analysis inputs not found! Please check the HTML.');
    return;
  }

  const priceValue = parseFloat(analysisPrice.value);
  const quantityValue = parseInt(analysisQuantity.value);

  console.log('Input values:', {priceValue, quantityValue});

  if (isNaN(priceValue) || isNaN(quantityValue) || priceValue <= 0 || quantityValue <= 0) {
    alert('Please enter valid positive values for price and quantity.');
    return;
  }

  const {
    demandAxis,
    supplierProfits,
    retailerProfits,
    expectedDemand,
    expectedSupplierProfit,
    expectedRetailerProfit
  } = buildProfitSeries(priceValue, quantityValue);

  const ctx = document.getElementById('profitLineChart');
  if (!ctx) {
    alert('Canvas element "profitLineChart" not found! Please check the HTML.');
    console.error('Canvas element profitLineChart not found!');
    return;
  }

  console.log('Creating chart with data points:', demandAxis.length);

  // Destroy existing chart if it exists
  if (profitLineChart) {
    profitLineChart.destroy();
  }

  profitLineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: demandAxis,
      datasets: [
        {
          label: 'Supplier Profit',
          data: supplierProfits,
          borderColor: 'rgba(255, 99, 132, 1)',
          backgroundColor: 'rgba(255, 99, 132, 0.1)',
          borderWidth: 2,
          tension: 0.1,
          pointRadius: 0,
          fill: false
        },
        {
          label: 'Retailer Profit',
          data: retailerProfits,
          borderColor: 'rgba(54, 162, 235, 1)',
          backgroundColor: 'rgba(54, 162, 235, 0.1)',
          borderWidth: 2,
          tension: 0.1,
          pointRadius: 0,
          fill: false
        },
        // Expected profit horizontal lines (dashed)
        {
          label: 'E[π_Supplier]',
          data: demandAxis.map(() => expectedSupplierProfit),
          borderColor: 'rgba(255, 99, 132, 0.6)',
          backgroundColor: 'rgba(255, 99, 132, 0.1)',
          borderWidth: 1,
          borderDash: [6, 6],
          pointRadius: 0,
          fill: false
        },
        {
          label: 'E[π_Retailer]',
          data: demandAxis.map(() => expectedRetailerProfit),
          borderColor: 'rgba(54, 162, 235, 0.6)',
          backgroundColor: 'rgba(54, 162, 235, 0.1)',
          borderWidth: 1,
          borderDash: [6, 6],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        title: {
          display: true,
          text: `Profit vs Demand (P: €${selectedRetailPrice().toFixed(2)}, Price: €${priceValue.toFixed(2)}, Quantity: ${quantityValue})`
        },
        legend: {
          display: true,
          position: 'bottom'
        },
        tooltip: {
          callbacks: {
            label: function (context) {
              return `${context.dataset.label}: €${context.parsed.y.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Demand'
          },
          grid: {
            color: 'rgba(0, 0, 0, 0.1)'
          }
        },
        y: {
          title: {
            display: true,
            text: 'Profit (€)'
          },
          grid: {
            color: 'rgba(0, 0, 0, 0.1)'
          },
          ticks: {
            callback: function (value) {
              return '€' + value;
            }
          }
        }
      }
    }
  });

  console.log('Chart created successfully');

  // Update profit details
  updateProfitDetails(priceValue, quantityValue, expectedDemand, expectedSupplierProfit, expectedRetailerProfit);
}

function updateProfitDetails(graph_price, graph_quantity, expectedDemand, expectedSupplierProfit, expectedRetailerProfit) {
  const detailsDiv = document.getElementById('profit-details');
  if (!detailsDiv) {
    console.warn('profit-details div not found');
    return;
  }

  const totalExpectedProfit = expectedSupplierProfit + expectedRetailerProfit;
  const supplierShare = totalExpectedProfit > 0 ? (Math.max(0, expectedSupplierProfit) / Math.max(1, Math.max(0, expectedSupplierProfit) + Math.max(0, expectedRetailerProfit))) * 100 : 0;

  let html = `
    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 10px;">
      <h5>Analysis for P: €${selectedRetailPrice().toFixed(2)}, Price: €${graph_price.toFixed(2)}, Quantity: ${graph_quantity}</h5>
      <p><strong>Expected Units Sold:</strong> ${expectedDemand.toFixed(2)} units</p>
    </div>
    
    <div style="display: flex; gap: 20px; margin-bottom: 15px;">
      <div style="background-color: rgba(255, 99, 132, 0.1); padding: 10px; border-radius: 5px; flex: 1;">
        <h6 style="color: rgba(255, 99, 132, 1); margin-bottom: 5px;">Expected Supplier Profit</h6>
        <p style="font-size: 18px; font-weight: bold; margin: 0; color: ${expectedSupplierProfit < 0 ? '#dc3545' : 'inherit'};">
          €${expectedSupplierProfit.toFixed(2)}
        </p>
      </div>
      <div style="background-color: rgba(54, 162, 235, 0.1); padding: 10px; border-radius: 5px; flex: 1;">
        <h6 style="color: rgba(54, 162, 235, 1); margin-bottom: 5px;">Expected Retailer Profit</h6>
        <p style="font-size: 18px; font-weight: bold; margin: 0; color: ${expectedRetailerProfit < 0 ? '#dc3545' : 'inherit'};">
          €${expectedRetailerProfit.toFixed(2)}
        </p>
      </div>
    </div>
    
    <div style="background-color: #e9ecef; padding: 10px; border-radius: 5px;">
      <p><strong>Total Expected Profit:</strong> €${totalExpectedProfit.toFixed(2)}</p>
      ${totalExpectedProfit > 0 ?
      `<p><strong>Expected Profit Split:</strong> Supplier ${supplierShare.toFixed(1)}% / Retailer ${(100 - supplierShare).toFixed(1)}%</p>` :
      '<p style="color: orange;"><strong>Warning:</strong> No positive total expected profit.</p>'
  }
    </div>
  `;

  if (expectedSupplierProfit < 0 || expectedRetailerProfit < 0) {
    html += `
      <div style="background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin-top: 10px;">
        <strong> Warning:</strong> Negative expected profits detected. This deal may result in losses.
      </div>
    `;
  }

  detailsDiv.innerHTML = html;
}