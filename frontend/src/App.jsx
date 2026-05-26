import React, { useState, useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8000/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [records, setRecords] = useState([]);
  const [analytics, setAnalytics] = useState({
    scope_totals: { "Scope 1": 0, "Scope 2": 0, "Scope 3": 0 },
    facility_distribution: [],
    monthly_trends: [],
    status_counts: { pending: 0, suspicious: 0, approved: 0, rejected: 0, locked: 0 }
  });
  const [facilities, setFacilities] = useState([]);
  const [jobs, setJobs] = useState([]);
  
  // Selection & Detail Drawer
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [auditTrail, setAuditTrail] = useState([]);
  const [selectedRecordIds, setSelectedRecordIds] = useState([]);
  
  // Filtering & Searching States
  const [scopeFilter, setScopeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [facilityFilter, setFacilityFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  // Manual Edit Inputs
  const [editQty, setEditQty] = useState('');
  const [editUnit, setEditUnit] = useState('');
  const [editFacility, setEditFacility] = useState('');
  const [editStartDate, setEditStartDate] = useState('');
  const [editEndDate, setEditEndDate] = useState('');
  const [editReason, setEditReason] = useState('');
  const [editError, setEditError] = useState('');
  const [editSuccess, setEditSuccess] = useState(false);

  // Ingestion Upload States
  const [ingestSource, setIngestSource] = useState('SAP');
  const [uploadedFile, setUploadedFile] = useState(null);
  const [manualPaste, setManualPaste] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState({ type: '', text: '' });
  
  const fileInputRef = useRef(null);

  // Load basic configurations
  useEffect(() => {
    fetchFacilities();
    fetchAnalytics();
    fetchRecords();
    fetchJobs();
  }, []);

  // Reload records when filters are adjusted
  useEffect(() => {
    fetchRecords();
  }, [scopeFilter, statusFilter, facilityFilter]);

  // Fetch facilities
  const fetchFacilities = async () => {
    try {
      const res = await fetch(`${API_BASE}/facilities/`);
      const data = await res.json();
      setFacilities(data);
    } catch (e) {
      console.error("Failed to load facilities", e);
    }
  };

  // Fetch analytics summary
  const fetchAnalytics = async () => {
    try {
      const res = await fetch(`${API_BASE}/analytics/`);
      const data = await res.json();
      setAnalytics(data);
    } catch (e) {
      console.error("Failed to load analytics summaries", e);
    }
  };

  // Fetch active Ingestion Jobs
  const fetchJobs = async () => {
    try {
      const res = await fetch(`${API_BASE}/jobs/`);
      const data = await res.json();
      setJobs(data);
    } catch (e) {
      console.error("Failed to load jobs", e);
    }
  };

  // Fetch Normalized Activity records
  const fetchRecords = async () => {
    try {
      let url = `${API_BASE}/normalized-records/?`;
      if (scopeFilter) url += `scope=${scopeFilter}&`;
      if (statusFilter) url += `review_status=${statusFilter}&`;
      if (facilityFilter) url += `facility=${facilityFilter}&`;
      
      const res = await fetch(url);
      const data = await res.json();
      setRecords(data);
    } catch (e) {
      console.error("Failed to load records", e);
    }
  };

  // Load audit trail when drawer is opened
  const loadAuditTrail = async (recId) => {
    try {
      const res = await fetch(`${API_BASE}/normalized-records/${recId}/audit_trail/`);
      const data = await res.json();
      setAuditTrail(data);
    } catch (e) {
      console.error("Failed to load audit trails", e);
    }
  };

  // Open Drawer and prefill forms
  const selectRecord = (rec) => {
    setSelectedRecord(rec);
    setEditQty(rec.normalized_quantity);
    setEditUnit(rec.normalized_unit);
    setEditFacility(rec.facility || '');
    setEditStartDate(rec.start_date);
    setEditEndDate(rec.end_date);
    setEditReason('');
    setEditError('');
    setEditSuccess(false);
    loadAuditTrail(rec.id);
  };

  // Handle manual records edit submission
  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editReason.trim()) {
      setEditError("A mandatory auditor's change justification must be provided.");
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE}/normalized-records/${selectedRecord.id}/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          facility: editFacility || null,
          normalized_quantity: editQty,
          normalized_unit: editUnit,
          start_date: editStartDate,
          end_date: editEndDate,
          change_reason: editReason
        })
      });
      
      const data = await res.json();
      if (!res.ok) {
        setEditError(data.error || "Failed to update record.");
        return;
      }
      
      setEditSuccess(true);
      setEditError('');
      setEditReason('');
      
      // Refresh database records
      fetchRecords();
      fetchAnalytics();
      loadAuditTrail(selectedRecord.id);
      
      // Update selected record view
      setSelectedRecord(data);
    } catch (err) {
      setEditError("System failed to commit manual adjustments.");
    }
  };

  // Approve a single record
  const handleApprove = async (id) => {
    try {
      await fetch(`${API_BASE}/normalized-records/${id}/approve/`, { method: 'POST' });
      fetchRecords();
      fetchAnalytics();
      if (selectedRecord && selectedRecord.id === id) {
        setSelectedRecord({ ...selectedRecord, review_status: 'APPROVED' });
        loadAuditTrail(id);
      }
    } catch (e) {
      console.error("Failed to approve", e);
    }
  };

  // Reject a single record
  const handleReject = async (id, reasonText = "Rejected by analyst.") => {
    try {
      await fetch(`${API_BASE}/normalized-records/${id}/reject/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reasonText })
      });
      fetchRecords();
      fetchAnalytics();
      if (selectedRecord && selectedRecord.id === id) {
        setSelectedRecord({ ...selectedRecord, review_status: 'REJECTED' });
        loadAuditTrail(id);
      }
    } catch (e) {
      console.error("Failed to reject", e);
    }
  };

  // Bulk lock selection and cryptographically seal approved records
  const handleBulkLock = async () => {
    if (selectedRecordIds.length === 0) return;
    if (!window.confirm(`Are you sure you want to permanently lock and seal ${selectedRecordIds.length} approved environmental records for audit? This action is irreversible.`)) return;

    try {
      const res = await fetch(`${API_BASE}/normalized-records/bulk_lock/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_ids: selectedRecordIds })
      });
      
      const data = await res.json();
      alert(data.message);
      
      setSelectedRecordIds([]);
      fetchRecords();
      fetchAnalytics();
      
      if (selectedRecord && selectedRecordIds.includes(selectedRecord.id)) {
        setSelectedRecord(null); // Close drawer if locked
      }
    } catch (e) {
      console.error("Bulk lock failed", e);
    }
  };

  // Handle ingestion file upload
  const handleIngestUpload = async (e) => {
    e.preventDefault();
    if (!uploadedFile && !manualPaste.trim()) {
      setIngestMsg({ type: 'danger', text: 'Please select a source file or paste raw content.' });
      return;
    }
    
    setIsIngesting(true);
    setIngestMsg({ type: '', text: '' });

    try {
      const fd = new FormData();
      fd.append('source_type', ingestSource);
      
      if (uploadedFile) {
        fd.append('file', uploadedFile);
      } else {
        fd.append('file_content', manualPaste);
        fd.append('filename', ingestSource === 'TRAVEL' ? 'manual_concur.json' : 'manual_paste.csv');
      }

      const res = await fetch(`${API_BASE}/ingest/`, {
        method: 'POST',
        body: fd
      });
      
      const data = await res.json();
      setIsIngesting(false);

      if (data.status === 'FAILED') {
        setIngestMsg({ type: 'danger', text: `Failed to import: ${data.error_summary}` });
      } else {
        setIngestMsg({ type: 'success', text: data.message });
        setUploadedFile(null);
        setManualPaste('');
        if (fileInputRef.current) fileInputRef.current.value = '';
        
        // Refresh records and dashboard analytics
        fetchRecords();
        fetchAnalytics();
        fetchJobs();
      }
    } catch (err) {
      setIsIngesting(false);
      setIngestMsg({ type: 'danger', text: 'A fatal server error prevented file upload.' });
    }
  };

  // Handle checkbox selection
  const toggleRecordSelection = (id) => {
    if (selectedRecordIds.includes(id)) {
      setSelectedRecordIds(selectedRecordIds.filter(x => x !== id));
    } else {
      setSelectedRecordIds([...selectedRecordIds, id]);
    }
  };

  // Search filter
  const filteredRecords = records.filter(rec => {
    const sTerm = searchTerm.toLowerCase();
    return (
      rec.category.toLowerCase().includes(sTerm) ||
      rec.activity_type.toLowerCase().includes(sTerm) ||
      (rec.facility_details?.name || 'unmapped').toLowerCase().includes(sTerm)
    );
  });

  // Calculate carbon ratios for executive ring charts
  const scope1CO2 = analytics.scope_totals["Scope 1"];
  const scope2CO2 = analytics.scope_totals["Scope 2"];
  const scope3CO2 = analytics.scope_totals["Scope 3"];
  const totalCO2 = scope1CO2 + scope2CO2 + scope3CO2;

  // Percentage splits
  const pct1 = totalCO2 > 0 ? (scope1CO2 / totalCO2) * 100 : 0;
  const pct2 = totalCO2 > 0 ? (scope2CO2 / totalCO2) * 100 : 0;
  const pct3 = totalCO2 > 0 ? (scope3CO2 / totalCO2) * 100 : 0;

  return (
    <div className="app-container">
      {/* Brand Header */}
      <header className="header">
        <div className="brand">
          <div className="brand-logo">B</div>
          <div>
            <h1>Breathe ESG</h1>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Enterprise Ingestion & Auditor Review Dashboard</p>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <div className="ingest-tabs" style={{ marginBottom: 0 }}>
            <button 
              className={`ingest-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}
            >
              📊 Review Board
            </button>
            <button 
              className={`ingest-tab ${activeTab === 'ingest' ? 'active' : ''}`}
              onClick={() => setActiveTab('ingest')}
            >
              📥 Data Ingestion
            </button>
          </div>

          <div className="user-badge">
            <div className="user-avatar">A</div>
            <span>alex.analyst (Admin)</span>
          </div>
        </div>
      </header>

      {/* Main Review Cockpit tab */}
      {activeTab === 'dashboard' && (
        <>
          {/* Executive Analytics Metrics row */}
          <section className="metrics-row">
            <div className="glass-panel metric-card total-co2">
              <div className="metric-label">Total Audited Carbon</div>
              <div className="metric-value">
                {totalCO2.toLocaleString(undefined, { maximumFractionDigits: 1 })} 
                <span className="metric-unit"> kg CO₂e</span>
              </div>
              <div className="metric-footer">
                <span>Active Environmental Footprint</span>
                <span>100% Normalized</span>
              </div>
            </div>

            <div className="glass-panel metric-card scope-1">
              <div className="metric-label">Scope 1 (Direct Fuel)</div>
              <div className="metric-value">
                {scope1CO2.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                <span className="metric-unit"> kg</span>
              </div>
              <div className="metric-footer">
                <span>Stationary/Mobile Fuels</span>
                <span>{pct1.toFixed(1)}% share</span>
              </div>
            </div>

            <div className="glass-panel metric-card scope-2">
              <div className="metric-label">Scope 2 (Electricity)</div>
              <div className="metric-value">
                {scope2CO2.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                <span className="metric-unit"> kg</span>
              </div>
              <div className="metric-footer">
                <span>Prorated Utility Grids</span>
                <span>{pct2.toFixed(1)}% share</span>
              </div>
            </div>

            <div className="glass-panel metric-card scope-3">
              <div className="metric-label">Scope 3 (Travel & Goods)</div>
              <div className="metric-value">
                {scope3CO2.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                <span className="metric-unit"> kg</span>
              </div>
              <div className="metric-footer">
                <span>Flights, Lodging, Procurement</span>
                <span>{pct3.toFixed(1)}% share</span>
              </div>
            </div>
          </section>

          {/* Interactive Visualizations */}
          <section className="dashboard-grid" style={{ marginBottom: '2.5rem' }}>
            {/* SVG Monthly trends */}
            <div className="glass-panel span-8">
              <h3 style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between' }}>
                <span>Calendar-Prorated Emissions Trends</span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-dark)' }}>Monthly Aggregate Split (kg CO₂e)</span>
              </h3>
              
              <div className="svg-chart-container">
                {analytics.monthly_trends.length === 0 ? (
                  <p style={{ color: 'var(--text-dark)' }}>No normalized monthly entries found. Ingest utility portal CSVs to populate trends.</p>
                ) : (
                  <svg width="100%" height="100%" viewBox="0 0 600 200" preserveAspectRatio="none">
                    {/* Gridlines */}
                    <line x1="40" y1="20" x2="580" y2="20" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                    <line x1="40" y1="70" x2="580" y2="70" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                    <line x1="40" y1="120" x2="580" y2="120" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                    <line x1="40" y1="170" x2="580" y2="170" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />

                    {/* Chart Bars */}
                    {(() => {
                      const trendCounts = analytics.monthly_trends.length;
                      const colWidth = Math.min(50, 480 / trendCounts);
                      const maxVal = Math.max(...analytics.monthly_trends.map(t => t["Scope 1"] + t["Scope 2"] + t["Scope 3"]), 100);

                      return analytics.monthly_trends.map((t, idx) => {
                        const s1Val = t["Scope 1"];
                        const s2Val = t["Scope 2"];
                        const s3Val = t["Scope 3"];
                        
                        const h1 = (s1Val / maxVal) * 150;
                        const h2 = (s2Val / maxVal) * 150;
                        const h3 = (s3Val / maxVal) * 150;
                        
                        const x = 50 + idx * (500 / trendCounts);
                        const y1 = 170 - h1;
                        const y2 = y1 - h2;
                        const y3 = y2 - h3;

                        return (
                          <g key={t.month}>
                            {/* Stacked bar segments */}
                            {h1 > 0 && <rect x={x} y={y1} width={colWidth} height={h1} fill="var(--scope-1)" opacity="0.8" rx="2" />}
                            {h2 > 0 && <rect x={x} y={y2} width={colWidth} height={h2} fill="var(--scope-2)" opacity="0.8" rx="2" />}
                            {h3 > 0 && <rect x={x} y={y3} width={colWidth} height={h3} fill="var(--scope-3)" opacity="0.8" rx="2" />}
                            
                            {/* X-Axis labels */}
                            <text x={x + colWidth/2} y="190" fill="var(--text-dark)" fontSize="9" textAnchor="middle">
                              {t.month.substring(5) === '01' ? t.month : t.month.substring(5)}
                            </text>
                          </g>
                        );
                      });
                    })()}
                  </svg>
                )}
              </div>
              
              <div className="chart-legend">
                <div className="legend-item"><div className="legend-color" style={{ background: 'var(--scope-1)' }}></div> Scope 1 (Direct Fuel)</div>
                <div className="legend-item"><div className="legend-color" style={{ background: 'var(--scope-2)' }}></div> Scope 2 (Utility Grid)</div>
                <div className="legend-item"><div className="legend-color" style={{ background: 'var(--scope-3)' }}></div> Scope 3 (Value Chain)</div>
              </div>
            </div>

            {/* Facility Footprint breakdown */}
            <div className="glass-panel span-4">
              <h3 style={{ marginBottom: '1.25rem' }}>Emissions by Operating Facility</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', marginTop: '0.5rem' }}>
                {analytics.facility_distribution.length === 0 ? (
                  <p style={{ color: 'var(--text-dark)', padding: '2rem 0', textAlign: 'center' }}>No unmapped facility emissions recorded.</p>
                ) : (
                  analytics.facility_distribution.map(fac => {
                    const maxShare = Math.max(...analytics.facility_distribution.map(f => f.value), 1);
                    const barPct = (fac.value / maxShare) * 100;
                    
                    return (
                      <div key={fac.plant_code} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                          <span className="text-bold">{fac.name} <span style={{ color: 'var(--text-dark)', fontWeight: 'normal' }}>({fac.plant_code})</span></span>
                          <span style={{ color: 'var(--color-primary)' }}>{fac.value.toLocaleString(undefined, { maximumFractionDigits: 0 })} kg</span>
                        </div>
                        <div style={{ height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
                          <div 
                            style={{ 
                              height: '100%', 
                              width: `${barPct}%`, 
                              background: 'linear-gradient(90deg, var(--color-primary), #a855f7)', 
                              borderRadius: '4px',
                              boxShadow: '0 0 10px rgba(99, 102, 241, 0.5)'
                            }}
                          ></div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </section>

          {/* Core Analyst review board */}
          <section className="glass-panel span-12" style={{ border: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <div>
                <h2>Normalized activity review ledger</h2>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                  Select approved lines to lock and seal for environmental audits. Anomalies are highlighted in yellow/red pulsing tags.
                </p>
              </div>
              
              <div style={{ display: 'flex', gap: '1rem' }}>
                {selectedRecordIds.length > 0 && (
                  <button className="btn btn-primary" onClick={handleBulkLock} style={{ boxShadow: '0 0 15px rgba(99, 102, 241, 0.4)' }}>
                    🔒 Lock & Seal Selected ({selectedRecordIds.length})
                  </button>
                )}
              </div>
            </div>

            {/* In-grid controls */}
            <div className="grid-controls">
              <div className="filters">
                <select className="select-filter" value={scopeFilter} onChange={e => setScopeFilter(e.target.value)}>
                  <option value="">All Scopes</option>
                  <option value="SCOPE_1">Scope 1 (Direct)</option>
                  <option value="SCOPE_2">Scope 2 (Indirect)</option>
                  <option value="SCOPE_3">Scope 3 (Value Chain)</option>
                </select>

                <select className="select-filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                  <option value="">All Review Statuses</option>
                  <option value="PENDING_REVIEW">Pending Review</option>
                  <option value="SUSPICIOUS">⚠️ Anomalies / Suspicious</option>
                  <option value="APPROVED">Approved</option>
                  <option value="REJECTED">Rejected</option>
                </select>

                <select className="select-filter" value={facilityFilter} onChange={e => setFacilityFilter(e.target.value)}>
                  <option value="">All Facilities</option>
                  {facilities.map(f => (
                    <option key={f.id} value={f.id}>{f.name} ({f.plant_code})</option>
                  ))}
                </select>
              </div>

              <input 
                type="text" 
                className="search-input" 
                placeholder="🔍 Search category or activity..." 
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>

            {/* Data Table */}
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: '40px' }}><span style={{ color: 'var(--text-dark)' }}>Select</span></th>
                    <th>Scope</th>
                    <th>Facility</th>
                    <th>Category</th>
                    <th>Activity Type</th>
                    <th>Start Date</th>
                    <th>End Date</th>
                    <th className="text-right">Normalized Qty</th>
                    <th>Unit</th>
                    <th className="text-right">Carbon Equivalent</th>
                    <th>Status</th>
                    <th>Lineage</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRecords.length === 0 ? (
                    <tr>
                      <td colSpan="12" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                        No environmental activity records found. Ingest some files in the Data Ingestion tab!
                      </td>
                    </tr>
                  ) : (
                    filteredRecords.map(rec => {
                      const isSelected = selectedRecordIds.includes(rec.id);
                      
                      return (
                        <tr 
                          key={rec.id} 
                          className={selectedRecord && selectedRecord.id === rec.id ? 'row-selected' : ''}
                          style={{ cursor: 'pointer' }}
                        >
                          <td onClick={(e) => e.stopPropagation()}>
                            {!rec.is_locked ? (
                              <input 
                                type="checkbox" 
                                checked={isSelected} 
                                onChange={() => toggleRecordSelection(rec.id)}
                                style={{ transform: 'scale(1.2)', cursor: 'pointer' }}
                              />
                            ) : (
                              <span style={{ fontSize: '0.85rem' }}>🔒</span>
                            )}
                          </td>
                          <td onClick={() => selectRecord(rec)}>
                            <span className={`badge badge-scope-${rec.scope.toLowerCase().replace('_', '-')}`}>
                              {rec.scope.replace('_', ' ')}
                            </span>
                          </td>
                          <td onClick={() => selectRecord(rec)} className="text-bold">
                            {rec.facility_details?.plant_code || <span style={{ color: 'var(--status-rejected)' }}>UNMAPPED</span>}
                          </td>
                          <td onClick={() => selectRecord(rec)}>{rec.category}</td>
                          <td onClick={() => selectRecord(rec)} className="text-bold">{rec.activity_type}</td>
                          <td onClick={() => selectRecord(rec)}>{rec.start_date}</td>
                          <td onClick={() => selectRecord(rec)}>{rec.end_date}</td>
                          <td onClick={() => selectRecord(rec)} className="text-right text-bold">
                            {parseFloat(rec.normalized_quantity).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </td>
                          <td onClick={() => selectRecord(rec)} style={{ color: 'var(--text-dark)' }}>{rec.normalized_unit}</td>
                          <td onClick={() => selectRecord(rec)} className="text-right text-bold" style={{ color: 'var(--color-primary)' }}>
                            {parseFloat(rec.co2e_kg).toLocaleString(undefined, { maximumFractionDigits: 1 })} kg CO₂e
                          </td>
                          <td onClick={() => selectRecord(rec)}>
                            <span className={`badge badge-${rec.review_status.toLowerCase()}`}>
                              {rec.review_status === 'PENDING_REVIEW' ? 'Pending' : rec.review_status.replace('_', ' ')}
                            </span>
                          </td>
                          <td>
                            <button className="btn btn-secondary" onClick={() => selectRecord(rec)} style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}>
                              🔍 View
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* Ingestion Center Tab */}
      {activeTab === 'ingest' && (
        <section className="dashboard-grid">
          {/* File Upload Zone */}
          <div className="glass-panel span-6">
            <h2>Data Ingest Center</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '1.5rem', marginTop: '0.2rem' }}>
              Load raw source systems. Supported formats: SAP ALV flat-file CSV grids, PG&E Utility CSV files, and corporate travel itinerary JSONs.
            </p>

            <form onSubmit={handleIngestUpload} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div className="edit-input-group">
                <label>Select Raw Source Pipeline</label>
                <div className="ingest-tabs">
                  <button 
                    type="button" 
                    className={`ingest-tab ${ingestSource === 'SAP' ? 'active' : ''}`}
                    onClick={() => { setIngestSource('SAP'); setUploadedFile(null); }}
                  >
                    🛠️ SAP Fuel ERP
                  </button>
                  <button 
                    type="button" 
                    className={`ingest-tab ${ingestSource === 'UTILITY' ? 'active' : ''}`}
                    onClick={() => { setIngestSource('UTILITY'); setUploadedFile(null); }}
                  >
                    ⚡ Utility Billing
                  </button>
                  <button 
                    type="button" 
                    className={`ingest-tab ${ingestSource === 'TRAVEL' ? 'active' : ''}`}
                    onClick={() => { setIngestSource('TRAVEL'); setUploadedFile(null); }}
                  >
                    ✈️ Concur JSON API
                  </button>
                </div>
              </div>

              {/* Upload Card */}
              <div className="edit-input-group">
                <label>Upload Source File</label>
                <div className="upload-zone" onClick={() => fileInputRef.current?.click()}>
                  <div className="upload-icon">📥</div>
                  <p className="text-bold">
                    {uploadedFile ? `Selected: ${uploadedFile.name}` : `Drag and drop or click to select ${ingestSource === 'TRAVEL' ? 'JSON' : 'CSV'} export`}
                  </p>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-dark)', marginTop: '0.4rem' }}>
                    {ingestSource === 'SAP' && 'Requires WERKS, BUDAT, MATNR, MAKTX columns'}
                    {ingestSource === 'UTILITY' && 'Handles PG&E Billing Period overlapping date CSVs'}
                    {ingestSource === 'TRAVEL' && 'Handles Concur segment booking nested itineraries'}
                  </p>
                  <input 
                    type="file" 
                    ref={fileInputRef}
                    style={{ display: 'none' }} 
                    accept={ingestSource === 'TRAVEL' ? '.json' : '.csv'}
                    onChange={e => {
                      if (e.target.files && e.target.files.length > 0) {
                        setUploadedFile(e.target.files[0]);
                        setManualPaste('');
                      }
                    }}
                  />
                </div>
              </div>

              {/* Paste Backup Option */}
              <div className="edit-input-group">
                <label>Or Paste Raw Text (Backup)</label>
                <textarea 
                  className="paste-area" 
                  placeholder={ingestSource === 'TRAVEL' ? 'Paste Concur itinerary JSON segment list dump here...' : 'WERKS,BUDAT,MATNR,MAKTX,MENGE,MEINS...\nUS02,20260415,MAT-FUEL-01,Diesel Kraftstoff,12500,L...'}
                  value={manualPaste}
                  onChange={e => {
                    setManualPaste(e.target.value);
                    setUploadedFile(null);
                  }}
                />
              </div>

              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={isIngesting || (!uploadedFile && !manualPaste.trim())}
              >
                {isIngesting ? '⚙️ Normalized parsing...' : '🚀 Ingest and Normalize Activity'}
              </button>

              {ingestMsg.text && (
                <div 
                  className="badge" 
                  style={{ 
                    display: 'block', 
                    padding: '0.8rem', 
                    borderRadius: '8px', 
                    textAlign: 'left',
                    background: ingestMsg.type === 'success' ? 'rgba(46, 213, 115, 0.15)' : 'rgba(255, 71, 87, 0.15)',
                    color: ingestMsg.type === 'success' ? '#2ed573' : '#ff6b81',
                    border: ingestMsg.type === 'success' ? '1px solid rgba(46, 213, 115, 0.3)' : '1px solid rgba(255, 71, 87, 0.3)'
                  }}
                >
                  <p className="text-bold" style={{ marginBottom: '0.2rem' }}>
                    {ingestMsg.type === 'success' ? '✔ Ingestion Succeeded' : '❌ Ingestion Failed'}
                  </p>
                  <p style={{ textTransform: 'none', fontWeight: 'normal', fontSize: '0.8rem' }}>{ingestMsg.text}</p>
                </div>
              )}
            </form>
          </div>

          {/* Job Pipeline Tracker */}
          <div className="glass-panel span-6">
            <h2>Active Pipeline Jobs Log</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '1.25rem', marginTop: '0.2rem' }}>
              Track history of data uploads. Complete lineage records mapping raw files to finalized greenhouse gas balances.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto', maxHeight: '480px' }}>
              {jobs.length === 0 ? (
                <p style={{ color: 'var(--text-dark)', padding: '2rem 0', textAlign: 'center' }}>No active ingestion pipeline logs recorded.</p>
              ) : (
                jobs.map(job => (
                  <div key={job.id} className="job-item">
                    <div>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <span className="text-bold">{job.source_type} Import</span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dark)' }}>Job ID: #{job.id}</span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                        File: {job.filename} | Imported by: {job.ingested_by_username}
                      </div>
                      {job.error_summary && (
                        <div style={{ fontSize: '0.7rem', color: '#ff6b81', marginTop: '0.4rem', background: 'rgba(255,71,87,0.05)', padding: '0.4rem', borderRadius: '4px', fontFamily: 'monospace' }}>
                          Err: {job.error_summary}
                        </div>
                      )}
                    </div>

                    <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: '0.4rem', alignItems: 'flex-end' }}>
                      <span className={`badge ${job.status === 'SUCCESS' ? 'badge-approved' : job.status === 'FAILED' ? 'badge-rejected' : 'badge-pending'}`}>
                        {job.status}
                      </span>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-dark)' }}>
                        Parsed rows: {job.raw_records_count} ({job.success_records_count} normalized)
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      )}

      {/* Analyst Inspection Drawer Panel */}
      {selectedRecord && (
        <div className="drawer-backdrop" onClick={() => setSelectedRecord(null)}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-header">
              <div>
                <h2>Activity Inspector</h2>
                <span className={`badge badge-scope-${selectedRecord.scope.toLowerCase().replace('_', '-')}`} style={{ marginTop: '0.4rem' }}>
                  {selectedRecord.scope.replace('_', ' ')}
                </span>
              </div>
              <button className="drawer-close" onClick={() => setSelectedRecord(null)}>×</button>
            </div>

            <div className="drawer-content">
              {/* If locked, display tamper-proof auditor seal */}
              {selectedRecord.is_locked && (
                <div 
                  className="badge" 
                  style={{ 
                    display: 'block', 
                    padding: '0.8rem', 
                    background: 'rgba(255,255,255,0.05)',
                    color: '#ffffff',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: '8px'
                  }}
                >
                  <p className="text-bold" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    🔒 CRYPTOGRAPHICALLY SEALED FOR environmental AUDIT
                  </p>
                  <p style={{ textTransform: 'none', fontWeight: '500', fontSize: '0.75rem', marginTop: '0.3rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                    SHA256: {selectedRecord.audit_seal_hash}
                  </p>
                </div>
              )}

              {/* Source Lineage Compare */}
              <div className="drawer-section">
                <h4 className="drawer-section-title">Raw Source Lineage (Lineage Ledger)</h4>
                <div className="lineage-grid">
                  {Object.entries(selectedRecord.raw_data_lineage).map(([k, v]) => (
                    <div key={k} className="lineage-item">
                      <span className="lineage-label">{k}</span>
                      <span className="lineage-val">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Normalized Data Details */}
              <div className="drawer-section">
                <h4 className="drawer-section-title">Engine Normalization Log</h4>
                <div className="lineage-grid">
                  <div className="lineage-item">
                    <span className="lineage-label">Standard Factor Used</span>
                    <span className="lineage-val">{selectedRecord.emission_factor_used}</span>
                  </div>
                  <div className="lineage-item">
                    <span className="lineage-label">Calculated Carbon equivalent</span>
                    <span className="lineage-val text-bold" style={{ color: 'var(--color-primary)' }}>
                      {parseFloat(selectedRecord.co2e_kg).toFixed(2)} kg CO₂e
                    </span>
                  </div>
                  {selectedRecord.suspicious_reason && (
                    <div className="lineage-item" style={{ gridColumn: 'span 2', background: 'rgba(255,165,0,0.05)', padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,165,0,0.2)' }}>
                      <span className="lineage-label" style={{ color: 'var(--status-suspicious)' }}>⚠️ Suspicious Warning / Anomaly Report</span>
                      <span className="text-bold" style={{ fontSize: '0.75rem', color: 'var(--status-suspicious)' }}>{selectedRecord.suspicious_reason}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Revision History Logs */}
              <div className="drawer-section">
                <h4 className="drawer-section-title">Record Revision Log ({auditTrail.length})</h4>
                <div className="timeline">
                  {auditTrail.map((log) => (
                    <div key={log.id} className="timeline-item">
                      <div className={`timeline-dot timeline-dot-${log.action.toLowerCase()}`}></div>
                      <div className="timeline-body">
                        <div className="timeline-header">
                          <span className="text-bold">{log.action === 'CREATE' ? 'System Ingestion' : log.action === 'EDIT' ? 'Manual Modification' : log.action === 'APPROVE' ? 'Analyst Signoff' : log.action === 'REJECT' ? 'Analyst Rejection' : 'Auditor Locked'}</span>
                          <span className="timeline-time">{new Date(log.timestamp).toLocaleString()}</span>
                        </div>
                        <div style={{ color: 'var(--text-dark)', fontSize: '0.75rem' }}>
                          Action by: <span style={{ color: 'var(--text-muted)' }}>{log.user_username}</span>
                        </div>
                        <p className="timeline-comment">{log.change_reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Analyst Edit & Signoff Form */}
              {!selectedRecord.is_locked && (
                <div className="drawer-section" style={{ background: 'rgba(99, 102, 241, 0.03)', border: '1px solid rgba(99, 102, 241, 0.15)' }}>
                  <h4 className="drawer-section-title">Analyst Signoff Actions</h4>
                  
                  <form onSubmit={handleEditSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginTop: '0.5rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                      <div className="edit-input-group">
                        <label>Facility Mapped</label>
                        <select 
                          className="edit-field" 
                          value={editFacility}
                          onChange={e => setEditFacility(e.target.value)}
                        >
                          <option value="">Unmapped Facility</option>
                          {facilities.map(f => (
                            <option key={f.id} value={f.id}>{f.name} ({f.plant_code})</option>
                          ))}
                        </select>
                      </div>
                      
                      <div className="edit-input-group">
                        <label>Normalized Quantity</label>
                        <input 
                          type="number" 
                          className="edit-field" 
                          value={editQty}
                          onChange={e => setEditQty(e.target.value)}
                          step="0.0001"
                          required
                        />
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                      <div className="edit-input-group">
                        <label>Start Date</label>
                        <input 
                          type="date" 
                          className="edit-field" 
                          value={editStartDate}
                          onChange={e => setEditStartDate(e.target.value)}
                          required
                        />
                      </div>
                      
                      <div className="edit-input-group">
                        <label>End Date</label>
                        <input 
                          type="date" 
                          className="edit-field" 
                          value={editEndDate}
                          onChange={e => setEditEndDate(e.target.value)}
                          required
                        />
                      </div>
                    </div>

                    {/* Change Justification MANDATORY comment */}
                    <div className="edit-input-group">
                      <label style={{ color: 'var(--status-suspicious)' }}>Auditable Modification Comment (MANDATORY)</label>
                      <input 
                        type="text" 
                        className="edit-field"
                        placeholder="Detail why you are modifying this row (e.g. corrected raw plant code mismatch)..."
                        value={editReason}
                        onChange={e => setEditReason(e.target.value)}
                      />
                    </div>

                    {editError && (
                      <div style={{ color: '#ff6b81', fontSize: '0.75rem', fontWeight: 600 }}>❌ {editError}</div>
                    )}
                    {editSuccess && (
                      <div style={{ color: '#2ed573', fontSize: '0.75rem', fontWeight: 600 }}>✔ Record updated and re-normalized successfully!</div>
                    )}

                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                      <button type="submit" className="btn btn-secondary" style={{ flex: 1 }}>
                        💾 Commit Adjustments
                      </button>
                      
                      {selectedRecord.review_status !== 'APPROVED' && (
                        <button 
                          type="button" 
                          className="btn btn-success" 
                          style={{ flex: 0.8 }}
                          onClick={() => handleApprove(selectedRecord.id)}
                        >
                          ✔ Signoff Row
                        </button>
                      )}

                      {selectedRecord.review_status !== 'REJECTED' && (
                        <button 
                          type="button" 
                          className="btn btn-danger" 
                          style={{ flex: 0.8 }}
                          onClick={() => {
                            const r = prompt("Provide rejection reason:");
                            if (r) handleReject(selectedRecord.id, r);
                          }}
                        >
                          ✖ Reject Row
                        </button>
                      )}
                    </div>
                  </form>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
