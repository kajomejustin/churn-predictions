// Global variables
let churnChart, subscriptionChart, scatterChart, lineChart;
let currentTimeframe = '30';
let dataTable;
let isDarkMode = false;
let dashboardData = null;
let ws = null; // WebSocket instance

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function () {
    // Load saved settings
    const savedTheme = localStorage.getItem('dashboardTheme');
    if (savedTheme === 'dark') {
        toggleTheme(true);
    }
    
    initializeFilters();
    initializeSidebar();
    initializeEventListeners();
    initializeDashboard().then(() => {
        connectWebSocket(); // Connect WebSocket after dashboard is initialized
    });
});

// Initialize dashboard components
async function initializeDashboard() {
    showLoading();
    initializeCharts();
    try {
        await fetchChartData();
        initializeDataTable();
    } catch (error) {
        console.error('Error initializing dashboard:', error);
        showErrorNotification('Failed to load dashboard data. Please try refreshing the page.');
    } finally {
        hideLoading();
    }
}

// WebSocket connection
function connectWebSocket() {
    if (ws) ws.close(); // Close existing connection if any
    const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    ws = new WebSocket(protocol + window.location.host + "/ws/dashboard/");
    
    ws.onopen = function() {
        console.log("WebSocket connected");
    };
    
    ws.onmessage = function(event) {
        console.log("Received:", event.data);
        const message = JSON.parse(event.data);
        if (message.type === "predictions") {
            updateTable(message.data);
            updateCharts(message.data);
        } else if (message.type === "new_prediction") {
            addNewPrediction(message.data);
            updateChartsWithNewData(message.data);
        }
    };
    
    ws.onclose = function() {
        console.log("WebSocket disconnected, reconnecting...");
        setTimeout(connectWebSocket, 2000); // Retry after 2 seconds
    };
    
    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
        showErrorNotification('WebSocket connection failed. Real-time updates unavailable.');
    };
}

function updateTable(predictions) {
    if (dataTable) {
        dataTable.clear();
        dataTable.rows.add(predictions);
        dataTable.draw();
    }
}

function addNewPrediction(prediction) {
    if (dataTable) {
        dataTable.row.add(prediction).draw();
        showSuccessNotification("New prediction received");
    }
}

function updateChartsWithNewData(prediction) {
    fetchChartData(); // Refresh summary stats and charts
    if (churnChart && prediction.churn_prediction !== undefined) {
        const churnData = churnChart.data.datasets[0].data;
        if (prediction.churn_prediction === 1) {
            churnData[0] += 1;
        } else {
            churnData[1] += 1;
        }
        churnChart.update();
    }
    
    if (subscriptionChart && prediction.subscription_type) {
        const subLabels = subscriptionChart.data.labels;
        const subData = subscriptionChart.data.datasets[0].data;
        const subIndex = subLabels.indexOf(prediction.subscription_type);
        if (subIndex !== -1) {
            subData[subIndex] += 1;
        } else {
            subLabels.push(prediction.subscription_type);
            subData.push(1);
        }
        subscriptionChart.update();
    }
    
    if (scatterChart && prediction.tenure && prediction.total_spend) {
        const scatterDataset = prediction.churn_prediction === 1 ? scatterChart.data.datasets[1] : scatterChart.data.datasets[0];
        scatterDataset.data.push({ x: prediction.tenure, y: prediction.total_spend });
        scatterChart.update();
    }
    
    fetchChartData(); // Recompute line chart
}

// Initialize Chart.js instances with improved configurations
function initializeCharts() {
    try {
        churnChart = new Chart(document.getElementById('churnChart'), {
            type: 'bar',
            data: { 
                labels: ['Churn', 'No Churn'], 
                datasets: [{ label: 'Customers', data: [0, 0], backgroundColor: ['#f72585', '#4cc9f0'], borderColor: ['#f72585', '#4cc9f0'], borderWidth: 1 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: true, text: 'Customer Churn Distribution', font: { size: 16 } },
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) { return `${context.dataset.label}: ${context.raw}`; },
                            afterLabel: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? Math.round((context.raw / total) * 100) : 0;
                                return `Percentage: ${percentage}%`;
                            }
                        }
                    }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Number of Customers' } },
                    x: { title: { display: true, text: 'Churn Status' } }
                }
            }
        });

        subscriptionChart = new Chart(document.getElementById('subscriptionChart'), {
            type: 'pie',
            data: { labels: [], datasets: [{ data: [], backgroundColor: ['#FF6B6B', '#4ECDC4', '#FFD93D'], borderWidth: 1 }] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: true, text: 'Subscription Type Distribution', font: { size: 16 } },
                    legend: { position: 'right' },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });

        scatterChart = new Chart(document.getElementById('scatterChart'), {
            type: 'scatter',
            data: {
                datasets: [
                    { label: 'Retained Customers', data: [], backgroundColor: 'rgba(76, 201, 240, 0.8)', pointRadius: 6 },
                    { label: 'Churned Customers', data: [], backgroundColor: 'rgba(247, 37, 133, 0.8)', pointRadius: 6 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: true, text: 'Total Spend vs. Tenure', font: { size: 16 } },
                    tooltip: {
                        callbacks: { label: function(context) { return `Tenure: ${context.parsed.x} months, Spend: $${context.parsed.y.toFixed(2)}`; } }
                    }
                },
                scales: {
                    x: { title: { display: true, text: 'Tenure (months)' } },
                    y: { title: { display: true, text: 'Total Spend ($)' } }
                }
            }
        });

        lineChart = new Chart(document.getElementById('lineChart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'Average Spend', data: [], borderColor: '#4361ee', backgroundColor: 'rgba(67, 97, 238, 0.1)', fill: true, tension: 0.3 },
                    { label: 'Trend', data: [], borderColor: '#f72585', borderWidth: 2, borderDash: [5, 5], pointRadius: 0, fill: false }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { title: { display: true, text: 'Average Spend by Tenure', font: { size: 16 } } },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Average Spend ($)' } },
                    x: { title: { display: true, text: 'Tenure Group (months)' } }
                }
            }
        });
    } catch (error) {
        console.error('Error initializing charts:', error);
        showErrorNotification('Failed to initialize charts. Please check your browser console for details.');
    }
}

// Fetch chart data with all filters applied
function fetchChartData() {
    const subscriptionType = document.getElementById('subscriptionFilter').value;
    const ageRange = document.getElementById('ageFilter').value;
    const churnPrediction = document.getElementById('churnPredictionFilter').value;
    const url = `/dashboard-data/?timeframe=${currentTimeframe}&subscription_type=${encodeURIComponent(subscriptionType)}&age_range=${encodeURIComponent(ageRange)}&churn_prediction=${encodeURIComponent(churnPrediction)}`;

    return fetch(url)
        .then(response => {
            if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            if (!data) throw new Error('Empty response received from server');
            dashboardData = data;
            
            if (data.summary_stats) {
                document.getElementById('totalCustomers').textContent = data.summary_stats.total_customers || 0;
                document.getElementById('churnRate').textContent = (data.summary_stats.churn_rate || 0) + '%';
                document.getElementById('avgSpend').textContent = '$' + (data.summary_stats.avg_spend || 0).toFixed(2);
                updateRiskIndicator(parseFloat(data.summary_stats.churn_rate || 0));
            }
            
            updateCharts(data);
        })
        .catch(error => {
            console.error('Error fetching chart data:', error);
            throw error;
        });
}

// Update all charts with error handling
function updateCharts(data) {
    try {
        if (data.bar_chart_data && churnChart) {
            churnChart.data.labels = data.bar_chart_data.labels || ['Churn', 'No Churn'];
            churnChart.data.datasets[0].data = data.bar_chart_data.data || [0, 0];
            if (data.bar_chart_data.backgroundColor) {
                churnChart.data.datasets[0].backgroundColor = data.bar_chart_data.backgroundColor;
            }
            churnChart.update();
        }
        
        if (data.pie_chart_data && subscriptionChart) {
            subscriptionChart.data.labels = data.pie_chart_data.labels || [];
            subscriptionChart.data.datasets[0].data = data.pie_chart_data.data || [];
            if (data.pie_chart_data.backgroundColor && data.pie_chart_data.backgroundColor.length === data.pie_chart_data.data.length) {
                subscriptionChart.data.datasets[0].backgroundColor = data.pie_chart_data.backgroundColor;
            }
            subscriptionChart.update();
        }
        
        if (data.scatter_data && scatterChart) {
            const retainedCustomers = (data.scatter_data || [])
                .filter(item => item && item.churn === 0)
                .map(item => ({ x: item.tenure, y: item.total_spend }));
            const churnedCustomers = (data.scatter_data || [])
                .filter(item => item && item.churn === 1)
                .map(item => ({ x: item.tenure, y: item.total_spend }));
            scatterChart.data.datasets[0].data = retainedCustomers;
            scatterChart.data.datasets[1].data = churnedCustomers;
            scatterChart.update();
        }
        
        if (data.line_chart_data && lineChart) {
            lineChart.data.labels = data.line_chart_data.labels || [];
            lineChart.data.datasets[0].data = data.line_chart_data.data || [];
            if (data.line_chart_data.data && data.line_chart_data.data.length > 1) {
                try {
                    const trendData = calculateTrendline(data.line_chart_data.labels, data.line_chart_data.data);
                    lineChart.data.datasets[1].data = trendData;
                } catch (trendError) {
                    console.warn('Error calculating trendline:', trendError);
                    lineChart.data.datasets[1].data = [];
                }
            } else {
                lineChart.data.datasets[1].data = []; // Clear trendline if insufficient data
            }
            lineChart.update();
        }
    } catch (updateError) {
        console.error('Error updating charts:', updateError);
        showErrorNotification('Some charts could not be updated. Please try refreshing the page.');
    }
}

// Update risk indicator based on churn rate
function updateRiskIndicator(churnRate) {
    try {
        const riskIndicator = document.getElementById('churnRiskIndicator');
        if (!riskIndicator) return;
        
        const indicatorBar = riskIndicator.querySelector('.risk-indicator-bar');
        if (!indicatorBar) return;
        
        indicatorBar.style.width = Math.min(Math.max(0, churnRate), 100) + '%';
        
        riskIndicator.classList.remove('high-risk', 'medium-risk', 'low-risk');
        if (churnRate > 20) {
            riskIndicator.classList.add('high-risk');
        } else if (churnRate > 10) {
            riskIndicator.classList.add('medium-risk');
        } else {
            riskIndicator.classList.add('low-risk');
        }
    } catch (error) {
        console.warn('Error updating risk indicator:', error);
    }
}

// Calculate trendline for line chart (with safeguards)
function calculateTrendline(labels, data) {
    if (!labels || !data || labels.length < 2 || data.length < 2 || data.every(val => val === 0)) {
        return []; // Return empty array if data is insufficient or all zeros
    }
    
    try {
        const n = Math.min(labels.length, data.length);
        let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
        
        for (let i = 0; i < n; i++) {
            const y = typeof data[i] === 'number' ? data[i] : 0;
            sumX += i;
            sumY += y;
            sumXY += i * y;
            sumXX += i * i;
        }
        
        const denominator = (n * sumXX - sumX * sumX);
        if (denominator === 0) return data; // Avoid division by zero
        
        const slope = (n * sumXY - sumX * sumY) / denominator;
        const intercept = (sumY - slope * sumX) / n;
        
        return labels.map((_, i) => intercept + slope * i);
    } catch (error) {
        console.warn('Error in trendline calculation:', error);
        return [];
    }
}

// Initialize DataTable with server-side processing
function initializeDataTable() {
    try {
        const pageSize = parseInt(localStorage.getItem('defaultPageSize') || '10');
        if (dataTable) dataTable.destroy();
        
        dataTable = $('#predictionsTable').DataTable({
            processing: true,
            serverSide: true,
            scrollX: false,
            autoWidth: false,
            ajax: {
                url: '/get_predictions/',
                type: 'GET',
                data: function (d) {
                    d.subscription_type = document.getElementById('subscriptionFilter').value;
                    d.age_range = document.getElementById('ageFilter').value;
                    d.churn_prediction = document.getElementById('churnPredictionFilter').value;
                    d.timeframe = currentTimeframe;
                },
                error: function(xhr, error, thrown) {
                    console.error('DataTables AJAX error:', error, thrown);
                    showErrorNotification('Failed to load prediction data.');
                },
                dataSrc: function(json) {
                    return json.data || [];
                }
            },
            columns: [
                { data: 'customer_id', width: '8%', className: 'dt-left' },
                { data: 'tenure', width: '6%', className: 'dt-center' },
                { data: 'total_spend', width: '9%', className: 'dt-right', render: function (data) { return '$' + (parseFloat(data) || 0).toFixed(2); } },
                { data: 'age', width: '6%', className: 'dt-center' },
                { data: 'usage_frequency', width: '8%', className: 'dt-center' },
                { data: 'support_calls', width: '7%', className: 'dt-center' },
                { data: 'payment_delay', width: '8%', className: 'dt-center' },
                { data: 'last_interaction', width: '8%', className: 'dt-center' },
                {
                    data: 'churn_prediction', width: '10%', className: 'dt-center',
                    render: function (data, type, row) {
                        if (type === 'display') {
                            const riskLevel = calculateRiskLevel(row);
                            let badgeClass = 'bg-success', badgeText = 'Low Risk';
                            if (riskLevel > 0.7) { badgeClass = 'bg-danger'; badgeText = 'High Risk'; }
                            else if (riskLevel > 0.3) { badgeClass = 'bg-warning text-dark'; badgeText = 'Medium Risk'; }
                            return `<span class="badge ${badgeClass}">${badgeText}</span>`;
                        }
                        return data;
                    }
                },
                { data: 'subscription_type', width: '10%', className: 'dt-left' },
                { data: 'prediction_time', width: '15%', className: 'dt-center', render: function (data) { 
                    try { return new Date(data).toLocaleString(); } catch (e) { return data; } 
                } }
            ],
            columnDefs: [
                { orderable: true, targets: "_all" },
                { targets: '_all', createdCell: function (td, cellData) { $(td).attr('title', cellData); } }
            ],
            pageLength: pageSize,
            order: [[10, 'desc']],
            dom: 'Bfrtip',
            buttons: [
                { extend: 'csv', text: '<i class="fas fa-file-csv"></i> Export CSV', title: 'Churn_Predictions_' + new Date().toISOString().split('T')[0], className: 'btn-sm btn-primary' }
            ],
            language: {
                paginate: { previous: '<i class="fas fa-chevron-left"></i>', next: '<i class="fas fa-chevron-right"></i>' },
                processing: '<div class="spinner"></div> Loading...',
                emptyTable: 'No prediction data available',
                zeroRecords: 'No matching records found'
            },
            createdRow: function(row, data) {
                if (data && data.customer_id) {
                    $(row).attr('data-customer-id', data.customer_id);
                    $(row).on('click', function() { showCustomerDetails(data); });
                }
            },
            responsive: true,
            initComplete: function() {
                console.log('DataTable initialization complete');
                $('.buttons-csv').addClass('d-none');
                $('#predictionsTable').css('width', '100%');
                setTimeout(function() { dataTable.columns.adjust(); }, 100);
            }
        });

        $(window).on('resize', function() { if (dataTable) dataTable.columns.adjust(); });
        $('#predictionsTable').on('error.dt', function(e, settings, techNote, message) {
            console.error('DataTable error:', message);
            showErrorNotification('Error loading table data. Please try refreshing the page.');
        });
    } catch (error) {
        console.error('Error initializing DataTable:', error);
        showErrorNotification('Failed to initialize data table. Please check console for details.');
    }
}

// Calculate risk level for a customer
function calculateRiskLevel(customerData) {
    if (!customerData) return 0;
    try {
        if (customerData.churn_prediction === 1) {
            const tenure = typeof customerData.tenure === 'number' ? customerData.tenure : 0;
            const spend = typeof customerData.total_spend === 'number' ? customerData.total_spend : 0;
            const supportCalls = typeof customerData.support_calls === 'number' ? customerData.support_calls : 0;
            const paymentDelay = typeof customerData.payment_delay === 'number' ? customerData.payment_delay : 0;
            const factors = {
                tenure: Math.max(0, 1 - (tenure / 36)),
                spend: Math.min(1, spend / 1000),
                supportCalls: Math.min(1, supportCalls / 5),
                paymentDelay: Math.min(1, paymentDelay / 30)
            };
            return 0.7 + ((factors.tenure * 0.1) + (factors.spend * 0.1) + (factors.supportCalls * 0.05) + (factors.paymentDelay * 0.05));
        } else {
            return Math.random() * 0.3;
        }
    } catch (error) {
        console.warn('Error calculating risk level:', error);
        return 0;
    }
}

// Initialize filters and load saved settings
function initializeFilters() {
    try {
        document.getElementById('subscriptionFilter').value = '';
        document.getElementById('ageFilter').value = '';
        document.getElementById('churnPredictionFilter').value = '';
        
        const savedFilters = JSON.parse(localStorage.getItem('dashboardFilters') || '{}');
        if (savedFilters.subscriptionType) document.getElementById('subscriptionFilter').value = savedFilters.subscriptionType;
        if (savedFilters.ageRange) document.getElementById('ageFilter').value = savedFilters.ageRange;
        if (savedFilters.churnPrediction) document.getElementById('churnPredictionFilter').value = savedFilters.churnPrediction;
        if (savedFilters.timeframe) {
            currentTimeframe = savedFilters.timeframe;
            const timeframeDropdown = document.getElementById('timeframeDropdown');
            if (timeframeDropdown) timeframeDropdown.textContent = `Last ${currentTimeframe} Days`;
        }
        
        ['subscriptionFilter', 'ageFilter', 'churnPredictionFilter'].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.addEventListener('change', saveFilterSettings);
        });
    } catch (error) {
        console.warn('Error initializing filters:', error);
    }
}

// Save filter settings to localStorage
function saveFilterSettings() {
    try {
        const filters = {
            subscriptionType: document.getElementById('subscriptionFilter').value,
            ageRange: document.getElementById('ageFilter').value,
            churnPrediction: document.getElementById('churnPredictionFilter').value,
            timeframe: currentTimeframe
        };
        localStorage.setItem('dashboardFilters', JSON.stringify(filters));
    } catch (error) {
        console.warn('Error saving filter settings:', error);
    }
}

// Initialize sidebar functionality
function initializeSidebar() {
    try {
        const sidebar = document.getElementById('sidebar');
        const content = document.getElementById('content');
        const sidebarToggle = document.getElementById('sidebarToggle');
        
        if (!sidebar || !sidebarToggle) {
            console.warn('Sidebar elements not found in the DOM');
            return;
        }

        sidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            sidebar.classList.toggle('collapsed');
            if (content) content.classList.toggle('content-expanded', sidebar.classList.contains('collapsed'));
            document.body.classList.toggle('sidebar-collapsed', sidebar.classList.contains('collapsed'));
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            console.log('Sidebar toggle clicked, current state:', sidebar.classList.contains('collapsed') ? 'collapsed' : 'expanded');
        });
        
        const savedState = localStorage.getItem('sidebarCollapsed');
        if (savedState === 'true') {
            sidebar.classList.add('collapsed');
            if (content) content.classList.add('content-expanded');
            document.body.classList.add('sidebar-collapsed');
        } else {
            sidebar.classList.remove('collapsed');
            if (content) content.classList.remove('content-expanded');
            document.body.classList.remove('sidebar-collapsed');
        }
        
        const currentPath = window.location.hash || '#overview';
        const sidebarLinks = document.querySelectorAll('.sidebar a');
        sidebarLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === currentPath) link.classList.add('active');
            link.addEventListener('click', function() {
                sidebarLinks.forEach(l => l.classList.remove('active'));
                this.classList.add('active');
                if (window.innerWidth < 768) {
                    sidebar.classList.add('collapsed');
                    if (content) content.classList.add('content-expanded');
                    document.body.classList.add('sidebar-collapsed');
                }
            });
        });
    } catch (error) {
        console.error('Error initializing sidebar:', error);
    }
}

// Initialize event listeners for filters and buttons
function initializeEventListeners() {
    try {
        ['subscriptionFilter', 'ageFilter', 'churnPredictionFilter'].forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => {
                    showLoading();
                    Promise.all([
                        fetchChartData().catch(error => {
                            console.error('Error fetching chart data:', error);
                            showErrorNotification('Failed to update charts with new filters');
                        }),
                        new Promise(resolve => {
                            if (dataTable) dataTable.ajax.reload(resolve, false);
                            else resolve();
                        })
                    ]).finally(hideLoading);
                });
            }
        });
        
        document.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                const onclick = this.getAttribute('onclick');
                if (onclick) {
                    const daysMatch = onclick.match(/'(\d+)'/);
                    if (daysMatch && daysMatch[1]) setTimeframe(daysMatch[1]);
                }
            });
        });
        
        const exportBtn = document.getElementById('exportCSVBtn');
        if (exportBtn) exportBtn.addEventListener('click', () => $('.buttons-csv').click());
        
        const refreshBtn = document.querySelector('.refresh-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', refreshData);
        
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) themeToggle.addEventListener('click', () => toggleTheme());
        
        document.querySelectorAll('.sidebar a').forEach(link => {
            link.addEventListener('click', function() {
                document.querySelectorAll('.sidebar a').forEach(l => l.classList.remove('active'));
                this.classList.add('active');
                if (window.innerWidth < 768) {
                    const sidebar = document.getElementById('sidebar');
                    if (sidebar) sidebar.classList.add('collapsed');
                    document.body.classList.add('sidebar-collapsed');
                }
            });
        });
    } catch (error) {
        console.warn('Error initializing event listeners:', error);
    }
}

// Set timeframe and refresh data
function setTimeframe(days) {
    if (!days) return;
    currentTimeframe = days;
    const timeframeDropdown = document.getElementById('timeframeDropdown');
    if (timeframeDropdown) timeframeDropdown.textContent = `Last ${days} Days`;
    
    try {
        const filters = JSON.parse(localStorage.getItem('dashboardFilters') || '{}');
        filters.timeframe = days;
        localStorage.setItem('dashboardFilters', JSON.stringify(filters));
    } catch (error) {
        console.warn('Error saving timeframe setting:', error);
    }
    
    refreshData();
}

// Refresh all data
function refreshData() {
    showLoading();
    Promise.all([
        fetchChartData().catch(error => {
            console.error('Error refreshing chart data:', error);
            showErrorNotification('Failed to refresh chart data');
            return null;
        }),
        new Promise(resolve => {
            if (dataTable) dataTable.ajax.reload(resolve, false);
            else resolve();
        })
    ])
    .then(results => {
        if (results[0] !== null) showSuccessNotification('Data refreshed successfully');
    })
    .finally(hideLoading);
}

// Toggle dark/light theme
function toggleTheme(forceDark = null) {
    try {
        isDarkMode = forceDark !== null ? forceDark : !isDarkMode;
        document.body.classList.toggle('dark-mode', isDarkMode);
        localStorage.setItem('dashboardTheme', isDarkMode ? 'dark' : 'light');
        updateChartsTheme(isDarkMode);
    } catch (error) {
        console.warn('Error toggling theme:', error);
    }
}

// Update chart theme based on dark mode
function updateChartsTheme(isDark) {
    try {
        const textColor = isDark ? '#f5f5f5' : '#212529';
        const gridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
        
        const updateOptions = (chart) => {
            if (!chart) return;
            if (chart.options && chart.options.scales) {
                if (chart.options.scales.x) {
                    chart.options.scales.x.ticks = { color: textColor };
                    chart.options.scales.x.grid = { color: gridColor };
                    if (chart.options.scales.x.title) chart.options.scales.x.title.color = textColor;
                }
                if (chart.options.scales.y) {
                    chart.options.scales.y.ticks = { color: textColor };
                    chart.options.scales.y.grid = { color: gridColor };
                    if (chart.options.scales.y.title) chart.options.scales.y.title.color = textColor;
                }
            }
            if (chart.options && chart.options.plugins) {
                if (chart.options.plugins.title) chart.options.plugins.title.color = textColor;
                if (chart.options.plugins.legend) chart.options.plugins.legend.labels = { color: textColor };
            }
            chart.update();
        };
        
        [churnChart, subscriptionChart, scatterChart, lineChart].forEach(updateOptions);
    } catch (error) {
        console.warn('Error updating chart theme:', error);
    }
}

// Show/hide loading overlay
function showLoading() { document.getElementById('loadingOverlay').classList.add('show'); }
function hideLoading() { document.getElementById('loadingOverlay').classList.remove('show'); }

// Notification functions
function showSuccessNotification(message) {
    try {
        const successToast = document.getElementById('successToast');
        const successToastMessage = document.getElementById('successToastMessage');
        if (successToast && successToastMessage) {
            successToastMessage.textContent = message;
            const bsToast = new bootstrap.Toast(successToast, { autohide: true, delay: 3000 });
            bsToast.show();
        } else console.log('Success:', message);
    } catch (error) {
        console.log('Success:', message);
    }
}

function showErrorNotification(message) {
    try {
        const errorToast = document.getElementById('errorToast');
        const errorToastMessage = document.getElementById('errorToastMessage');
        if (errorToast && errorToastMessage) {
            errorToastMessage.textContent = message;
            const bsToast = new bootstrap.Toast(errorToast, { autohide: true, delay: 5000 });
            bsToast.show();
        } else console.error('Error:', message);
    } catch (error) {
        console.error('Error:', message);
    }
}

// Download chart as image
function downloadChart(chartId, filename) {
    try {
        const canvas = document.getElementById(chartId);
        if (!canvas) {
            showErrorNotification('Chart not found');
            return;
        }
        const link = document.createElement('a');
        link.download = filename + '.png';
        link.href = canvas.toDataURL('image/png');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showSuccessNotification('Chart downloaded successfully');
    } catch (error) {
        console.error('Error downloading chart:', error);
        showErrorNotification('Failed to download chart');
    }
}

// Placeholder for customer details modal
function showCustomerDetails(customerData) {
    if (!customerData) return;
    console.log('Customer Details:', customerData);
    showSuccessNotification('Customer details view will be implemented in a future update.');
}