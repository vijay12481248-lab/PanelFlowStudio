/* Provider Management Screen - Phase 5
PanelFlow Studio Universal AI Gateway Provider Management UI

Features:
A. Provider Overview - Cards with status, capabilities, cost tier
B. Add Provider Wizard - Stepper: provider selection, credentials, endpoint, test
C. Model Explorer - Filterable table: provider/capability/price/limits
D. Intelligent Routing - Strategy selection, fallbacks, budget, privacy
E. Usage Dashboard - Charts: requests, success/failure, latency, cost, tokens
F. Diagnostics - Routing explanation, cooldown states, error categories
*/

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Box,
  Typography,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Select,
  MenuItem,
  Input,
  Box as FlexBox,
  Badge,
  Paper,
 Grid,
  Tooltip,
  Alert,
  TablePagination,
  LinearProgress,
  Link,
  Divider,
  Icons,
} from "@mui/material";
import { BarChart, Bar } from "react-chartjs-2";
import { useNavigate } from "react-router-dom";
import { useStore } from "@/store"; // Assuming store context
import { provider_registry, model_registry } from "@/engine/ai_gateway";
import { CapabilityType, RoutingStrategy } from "@/engine/ai_gateway/contracts";

// Material-UI theme variables from design tokens
const PRIMARY_500 = "#6366f1";
const PRIMARY_600 = "#4f46e5";
const SUCCESS_500 = "#10b981";
const WARNING_500 = "#f59e0b";
const ERROR_500 = "#ef4444";
INFO_500 = "#3b82f6";

const BG_PRIMARY = "#080b12";
const BG_SECONDARY = "#0c0e17";
const BG_TERTIARY = "#111422";
const TEXT_PRIMARY = "#fafafa";
const TEXT_SECONDARY = "#a1a1aa";
const TEXT_TERTIARY = "#71717a";

const useStyles = () => ({
  root: {
    backgroundColor: BG_PRIMARY,
    minHeight: "100vh",
    color: TEXT_PRIMARY,
  },
  toolbar: {
    backgroundColor: BG_SECONDARY,
    borderBottom: `1px solid ${BG_TERTIARY}`,
    padding: "16px 24px",
  },
  title: {
    fontSize: "1.5rem",
    fontWeight: 600,
  },
  card: {
    backgroundColor: BG_SECONDARY,
    border: `1px solid rgba(255,255,255,0.1)`,
    borderRadius: "16px",
    padding: "20px",
    marginBottom: "16px",
  },
  sectionTitle: {
    fontSize: "1rem",
    fontWeight: 500,
    marginBottom: "12px",
    color: TEXT_SECONDARY,
  },
  providerCard: {
    padding: "16px",
    borderRadius: "12px",
    cursor: "pointer",
    transition: "all 0.2s ease",
    "&:hover": {
      backgroundColor: "#141a2e",
      borderColor: "rgba(99, 102, 241, 0.3)",
    },
  },
  statusBadge: {
    marginRight: "8px",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "0.75rem",
    fontWeight: 500,
  },
  capabilityChip: {
    margin: "2px",
    fontSize: "0.7rem",
  },
  emptyState: {
    padding: "40px 20px",
    textAlign: "center",
    color: TEXT_TERTIARY,
  },
  input: {
    backgroundColor: BG_TERTIARY,
    border: `1px solid ${BG_TERTIARY}`,
    color: TEXT_PRIMARY,
    borderRadius: "12px",
    "&:focus": {
      backgroundColor: BG_TERTIARY,
      borderColor: PRIMARY_500,
      "& .MuiOutlinedInput-notchedOutline": {
        borderColor: PRIMARY_500,
      },
    },
  },
  select: {
    "& .MuiOutlinedInput-root": {
      backgroundColor: BG_TERTIARY,
      borderRadius: "12px",
    },
    "& .MuiInputLabel-root": {
      color: TEXT_SECONDARY,
    },
    "&.Mui-focused": {
      "& .MuiOutlinedInput-root": {
        borderColor: PRIMARY_500,
      },
    },
  },
  routingStrategyChip: {
    margin: "2px 4px 2px 0",
    padding: "4px 8px",
    borderRadius: "6px",
    fontSize: "0.75rem",
    fontWeight: 500,
    textTransform: "capitalize",
  },
  budgetInput: {
    margin: "4px",
    "& .MuiInputBase-input": {
      color: TEXT_PRIMARY,
      backgroundColor: BG_TERTIARY,
    },
  },
  chartContainer: {
    height: "200px",
    backgroundColor: BG_SECONDARY,
    borderRadius: "12px",
    padding: "12px",
  },
  loadingSpinner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "200px",
    color: TEXT_TERTIARY,
  },
  tableCell: {
    color: TEXT_SECONDARY,
    fontSize: "0.875rem",
  },
  tableHeadCell: {
    color: TEXT_TERTIARY,
    fontSize: "0.75rem",
    fontWeight: 600,
    textTransform: "uppercase",
  },
});

const ProviderManagementScreen = () => {
  const classes = useStyles();
  const navigate = useNavigate();
  const { setStatus, projects } = useStore();

  // State for each section
  const [section, setSection] = useState("overview");
  const [providers, setProviders] = useState([]);
  const [filteredProviders, setFilteredProviders] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [routingStrategy, setRoutingStrategy] = useState(RoutingStrategy.BALANCED);
  const [freeOnly, setFreeOnly] = useState(true);
  const [budget, setBudget] = useState("");
  const [modelFilters, setModelFilters] = useState({
    capability: "",
    priceTier: "all", // free, paid, all
  });

  // Load providers on mount
  useEffect(() => {
    const loadProviders = async () => {
      try {
        // Get providers from registry
        const regProviders = provider_registry.list_providers(enabled_only=true);
        const models = model_registry.get_models_by_capability(
          "text.generate",
          free_only=false
        );
        setProviders(regProviders);
        setFilteredProviders(regProviders);
      } catch (error) {
        console.error("Failed to load providers:", error);
      }
    };
    loadProviders();
  }, []);

  // Filter providers
  const filtered = useMemo(
    () =>
      searchQuery
        ? providers.filter(
            (p) =>
              p.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
              p.provider_id.toLowerCase().includes(searchQuery.toLowerCase())
          )
        : providers,
    [providers, searchQuery]
  );

  // Section handlers
  const handleSection = (newSection) => setSection(newSection);

  const overviewSection = (
    <Box component="div" sx={classes.root}>
      <Box sx={classes.toolbar}>
        <Typography variant="h6" className={classes.title}>
          Provider Management
        </Typography>
        <Button
          variant="outlined"
          onClick={() => navigate("/")}
          sx={{ mr: 2 }}
        >
          Back to Dashboard
        </Button>
        <Button
          variant="contained"
          sx={{ ml: "auto", mr: 2 }}
          onClick={() => setSection("add")}
        >
          Add Provider
        </Button>
      </Box>

      <Box sx={classes.sectionTitle}>Provider Overview</Typography>

      {providers.length === 0 ? (
        <Box sx={classes.emptyState}>
          <Typography variant="body2">
            No providers configured. Add a provider to get started.
          </Typography>
        </Box>
      ) : (
        <Box sx={classes.grid}>
          {filtered.map((provider) => (
            <Box
              key={provider.provider_id}
              sx={classes.providerCard}
              onClick={() => setSelectedProvider(provider.provider_id)}
            >
              <Box sx={({ theme }) => ({
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                mb: "12px",
              })}>
                <Box sx={({ theme }) => ({ flex: 1 })}>
                  <Typography variant="h6" gutterBottom>
                    {provider.display_name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {provider.provider_id}
                  </Typography>
                </Box>
                <Box>
                  <Chip
                    label={
                      provider.enabled
                        ? <Badge color="success">Enabled</Badge>
                        : <Badge color="error">Disabled</Badge>
                    }
                    sx={classes.statusBadge}
                  />
                </Box>
              </Box>

              <Box sx={({ theme }) => ({ display: "flex", gap: 2 })}>
                {provider.capabilities?.map((cap) => (
                  <Chip
                    key={cap}
                    label={cap}
                    sx={classes.capabilityChip}
                    size="small"
                  />
                ))}
              </Box>

              <Box sx={({ theme }) => ({
                marginTop: "8px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-end",
              })}>
                {provider.free_tier ? (
                  <Chip
                    label="Free-tier ✓"
                    sx={({ theme }) => ({
                      backgroundColor: "rgba(16, 185, 129, 0.2)",
                      color: SUCCESS_500,
                    })}
                  />
                ) : (
                  <Chip
                    label="Paid"
                    sx={({ theme }) => ({
                      backgroundColor: "rgba(239, 68, 68, 0.2)",
                      color: ERROR_500,
                    })}
                  />
                )}
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );

  const addProviderSection = () => {
    // Simplified add provider form
    return (
      <Box sx={classes.root}>
        <Box sx={classes.toolbar}>
          <Typography variant="h6" className={classes.title}>
            Add New Provider
          </Typography>
          <Button variant="outline" onClick={() => setSection("overview")}>
            Cancel
          </Button>
        </Box>

        <Box sx={classes.sectionTitle}>Provider Configuration</Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Provider Type</Typography>
          <Select
            defaultValue=""
            label="Provider"
            sx={classes.select}
            onChange={(e) => console.log("Provider selected:", e.target.value)}
          >
            <MenuItem value="ollama">
              Ollama Local
            </MenuItem>
            <MenuItem value="openai">
              OpenAI API
            </MenuItem>
            <MenuItem value="gemini">
              Google Gemini
            </MenuItem>
            <MenuItem value="freellm">
              FreeLLM / OpenAI-Compatible
            </MenuItem>
          </Select>
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">API Key</Typography>
          <Input
            type="password"
            placeholder="Enter API key (or leave blank for local)"
            sx={classes.input}
            disabled={true} // Will enable based on provider selection
          />
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Endpoint URL</Typography>
          <Input
            placeholder="http://127.0.0.1:11434 (Ollama)"
            sx={classes.input}
            disabled={true}
          />
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Model Name</Typography>
          <Input
            placeholder="e.g., gpt-4o, qwen3.5:9b"
            sx={classes.input}
          />
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1"></Typography>
          <Button
            variant="contained"
            sx={{ mt: "16px", width: "100%" }}
            onClick={() => setSection("overview")}
          >
            Test Connection
          </Button>
        </Box>
      </Box>
    );
  };

  const modelExplorerSection = () => {
    return (
      <Box sx={classes.root}>
        <Box sx={classes.toolbar}>
          <Typography variant="h6" className={classes.title}>
            Model Explorer
          </Typography>
          <Button variant="outline" onClick={() => setSection("overview")}>
            Back
          </Button>
        </Box>

        <Box sx={classes.sectionTitle}>
          Filter Models
          <Box sx={{ display: "flex", gap: "8px", my: "8px" }}>
            <Select
              sx={classes.select}
              label="Capability"
              onChange={(e) => setModelFilters((prev) => ({ ...prev, capability: e.target.value }))}
            >
              <MenuItem value="">All</MenuItem>
              {["text.generate", "text.structured", "vision.understand"].map((cap) => (
                <MenuItem key={cap} value={cap}>
                  {cap}
                </MenuItem>
              ))}
            </Select>

            <Select
              sx={classes.select}
              label="Price Tier"
              onChange={(e) =>
                setModelFilters((prev) => ({ ...prev, priceTier: e.target.value }))
              }
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="free">Free-tier only</MenuItem>
              <MenuItem value="paid">Paid only</MenuItem>
            </Select>
          </Box>
        </Box>

        <Box sx={classes.card}>
          {filteredProviders.length === 0 ? (
            <Box sx={classes.emptyState}>
              <Typography variant="body2">
                No models match the selected filters.
              </Typography>
            </Box>
          ) : (
            <Box sx={{ overflowX: "auto" }}>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow sx={classes.tableHeadCell}>
                      <TableCell>Model</TableCell>
                      <TableCell>Provider</TableCell>
                      <TableCell>Capabilities</TableCell>
                      <TableCell>Context</TableCell>
                      <TableCell>Pricing</TableCell>
                      <TableCell>Free-tier</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredProviders
                      .filter(
                        (m) =>
                          !modelFilters.capability ||
                          (m.capabilities || []).includes(modelFilters.capability)
                      )
                      .filter(
                        (m) =>
                          modelFilters.priceTier === "all" ||
                          (modelFilters.priceTier === "free" && m.free_tier) ||
                          (modelFilters.priceTier === "paid" && !m.free_tier)
                      )
                      .map((model) => (
                        <TableRow key={model.model_id} sx={classes.tableCell}>
                          <TableCell component="td">
                            <Typography variant="body2">
                              {model.display_name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {model.model_id}
                            </Typography>
                          </TableCell>
                          <TableCell component="td">
                            <Typography variant="caption" color="text.secondary">
                              {model.provider_id}
                            </Typography>
                          </TableCell>
                          <TableCell component="td">
                            {model.capabilities
                              ?.map((c) => (
                                <Chip
                                  key={c}
                                  label={c}
                                  size="small"
                                  sx={classes.capabilityChip}
                                />
                              ))}
                            {!model.capabilities && (
                              <Typography variant="caption" color="text.secondary">
                                Basic
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell component="td">
                            {model.context_window} tokens
                          </TableCell>
                          <TableCell component="td">
                            {model.pricing_input_per_million}
                              ? `$${model.pricing_input_per_million.toString()}/1M input`
                              : "Free"
                          </TableCell>
                          <TableCell component="td">
                            {model.free_tier ? "Yes" : "No"}
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </Box>
      </Box>
    );
  };

  const routingSection = () => {
    return (
      <Box sx={classes.root}>
        <Box sx={classes.toolbar}>
          <Typography variant="h6" className={classes.title}>
            Intelligent Routing
          </Typography>
          <Button variant="outline" onClick={() => setSection("overview")}>
            Back
          </Button>
        </Box>

        <Box sx={classes.sectionTitle}>Routing Strategy</Box>

        <Box sx={classes.card}>
          {Object.values(RoutingStrategy).map((strategy) => (
            <Box
              key={strategy}
              sx={({ theme, ownerState }) => ({
                ...classes.routingStrategyChip,
                backgroundColor:
                  ownerState.selectedStrategy === strategy
                    ? PRIMARY_500
                    : BG_TERTIARY,
                color:
                  ownerState.selectedStrategy === strategy
                    ? BG_PRIMARY
                    : TEXT_SECONDARY,
              })}
            >
              <Typography
                variant="body2"
                component="span"
                style={{ whiteSpace: "nowrap" }}
              >
                {strategy}
              </Typography>
            </Box>
          ))}
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Free-only Policy</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Chip
              label="Free-only ✓"
              sx={({ theme }) => ({
                backgroundColor: "rgba(16, 185, 129, 0.2)",
                color: SUCCESS_500,
              })}
            />
            <Typography variant="body2" color="text.secondary">
              Paid inference disabled by default
            </Typography>
          </Box>
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Budget Settings</Typography>
          <Input
            placeholder="Global budget in USD (e.g., 50.00)"
            type="number"
            sx={classes.budgetInput}
            onChange={(e) => setBudget(e.target.value)}
          />
          <Typography variant="caption" color="text.secondary">
            Sets maximum monthly spend across all providers
          </Typography>
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Privacy Rules</Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <Box>
              <Typography variant="body2" color="text-secondary">
                Local-only processing:
              </Typography>
              <Chip
                label="Enabled"
                sx={({ theme }) => ({
                  backgroundColor: "rgba(16, 185, 129, 0.2)",
                  color: SUCCESS_500,
                })}
              />
            </Box>
            <Box>
              <Typography variant="body2" color="text-secondary">
                Allow cloud provider transmission:
              </Typography>
              <Chip
                label="Ask per request"
                sx={({ theme }) => ({
                  backgroundColor: "rgba(59, 130, 246, 0.2)",
                  color: INFO_500,
                })}
              />
            </Box>
          </Box>
        </Box>
      </Box>
    );
  };

  const usageDashboardSection = () => {
    // In a real implementation, this would fetch actual usage data
    // from the usage_records database table
    const mockData = {
      labels: ["Ollama", "OpenAI", "Gemini", "FreeLLM"],
      datasets: [
        {
          label: "Requests",
          data: [120, 85, 43, 210],
          backgroundColor: [PRIMARY_500, INFO_500, SUCCESS_500, WARNING_500],
        },
        {
          label: "Success Rate",
          data: [98, 95, 92, 99],
          type: "line",
          fill: false,
          borderColor: [PRIMARY_500, INFO_500, SUCCESS_500, WARNING_500],
          tension: 0.1,
        },
      ],
    };

    return (
      <Box sx={classes.root}>
        <Box sx={classes.toolbar}>
          <Typography variant="h6" className={classes.title}>
            Usage Dashboard
          </Typography>
          <Button variant="outline" onClick={() => setSection("overview")}>
            Back
          </Button>
        </Box>

        <Box sx={classes.sectionTitle}>Request Volume</Box>
        <Box sx={classes.chartContainer}>
          <BarChart data={mockData} options={{ responsive: true }} />
        </Box>

        <Box sx={classes.sectionTitle}>Cost Analysis</Box>
        <Box sx={classes.chartContainer}>
          {/* Cost bar chart would go here */}
          <Typography variant="body2" color="text.secondary">
            Cost data not available - configure providers to enable tracking
          </Typography>
        </Box>

        <Box sx={classes.sectionTitle}>Latency</Box>
        <Box sx={classes.chartContainer}>
          {/* Latency chart would go here */}
          <Typography variant="body2" color="text.secondary">
            Latency data not available
          </Typography>
        </Box>
      </Box>
    );
  };

  const diagnosticsSection = () => {
    return (
      <Box sx={classes.root}>
        <Box sx={classes.toolbar}>
          <Typography variant="h6" className={classes.title}>
            Diagnostics
          </Typography>
          <Button variant="outline" onClick={() => setSection("overview")}>
            Back
          </Button>
        </Box>

        <Box sx={classes.sectionTitle}>Routing Explanation</Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Why a model was selected:</Typography>
          <Typography variant="body2" color="text-secondary" mb="8">
            Selected Ollama qwen3.5:9b via LOCAL_FIRST strategy;
            OpenAI excluded due to free-only policy;
            Groq excluded (no vision support);
            Gemini excluded (budget constraint active)
          </Typography>

          <Typography variant="body1" mb="8">Why other models were excluded:</Typography>
          <Typography variant="body2" color="text-secondary" mb="8">
            - OpenAI: Paid model blocked by free-only policy
            - Groq: No vision capabilities for panel analysis task
            - Gemini: Budget constraint at 85% of global limit
            - Local models: Disabled in provider configuration
          </Typography>
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Provider Health Status</Typography>
          {selectedProvider && (
            <>
              <Typography variant="body2" color="text-secondary">
                Provider: {selectedProvider}
              </Typography>
              <Typography variant="body2" color="text-secondary">
                Health: <Chip
                  label={"HEALTHY"}
                  sx={({ theme }) => ({
                    backgroundColor: "rgba(16, 185, 129, 0.2)",
                    color: SUCCESS_500,
                  })}
                />
              </Typography>
              <Typography variant="body2" color="text-secondary">
                Cooldown: None
              </Typography>
              <Typography variant="body2" color="text-secondary">
                Rate limit: N/A (local endpoint)
              </Typography>
            </>
          )}
        </Box>

        <Box sx={classes.card}>
          <Typography variant="body1">Error Categories</Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            <Chip
              label="Rate limit"
              sx={({ theme }) => ({
                backgroundColor: "rgba(251, 191, 36, 0.2)",
                color: WARNING_500,
              })}
            />
            <Chip
              label="Transient"
              sx={({ theme }) => ({
                backgroundColor: "rgba(16, 185, 129, 0.2)",
                color: SUCCESS_500,
              })}
            />
            <Chip
              label="Auth error"
              sx={({ theme }) => ({
                backgroundColor: "rgba(239, 68, 68, 0.2)",
                color: ERROR_500,
              })}
            />
            <Chip
              label="Unsupported"
              sx={({ theme }) => ({
                backgroundColor: "rgba(124, 58, 237, 0.2)",
                color: PRIMARY_500,
              })}
            />
          </Box>
        </Box>
      </Box>
    );
  };

  // Render sections
  const sections = {
    overview: overviewSection,
    add: addProviderSection,
    models: modelExplorerSection,
    routing: routingSection,
    usage: usageDashboardSection,
    diagnostics: diagnosticsSection,
  };

  return (
    <Box sx={classes.root}>
      <Box sx={classes.toolbar}>
        <Typography variant="h6" className={classes.title}>
          AI Provider Management
        </Typography>
      </Box>

      {sections[section]()}
    </Box>
  );
};

export default ProviderManagementScreen;