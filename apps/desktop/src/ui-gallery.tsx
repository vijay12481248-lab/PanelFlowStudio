import React from "react";
import ReactDOM from "react-dom/client";
import { Home, FolderKanban, Sparkles, Activity, BookOpen, SlidersHorizontal } from "lucide-react";
import {
  Button, Chip, Dialog, Dock, Drawer, EmptyState, EngineStatus, ErrorState, Field, GlassPanel, IconButton,
  InboxRow, Input, JobCard, ListRow, Menu, PageHeader, Progress, Select, Skeleton, Stepper, Switch, Tabs,
  Tile, ToastProvider, Tooltip, useToast,
} from "@panelflow/ui-v2";
import "./index.css";

const DOCK = [
  { id: "home", label: "Home", icon: <Home size={20} />, href: "#home" },
  { id: "projects", label: "Projects", icon: <FolderKanban size={20} />, href: "#projects" },
  { id: "create", label: "Create", icon: <Sparkles size={20} />, href: "#create" },
  { id: "jobs", label: "Jobs", icon: <Activity size={20} />, href: "#jobs" },
  { id: "library", label: "Library", icon: <BookOpen size={20} />, href: "#library" },
  { id: "settings", label: "Settings", icon: <SlidersHorizontal size={20} />, href: "#settings" },
];

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="grid gap-3">
    <h2 className="font-display text-base font-semibold text-fg-dim">{title}</h2>
    {children}
  </section>
);

const Overlays: React.FC = () => {
  const [dialog, setDialog] = React.useState(false);
  const [drawer, setDrawer] = React.useState(false);
  const toast = useToast();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="secondary" onClick={() => setDialog(true)}>Open dialog</Button>
      <Button variant="secondary" onClick={() => setDrawer(true)}>Open drawer</Button>
      <Button variant="secondary" onClick={() => toast.show("Settings saved", "ok")}>Show toast</Button>
      <Menu trigger={<Button variant="ghost">Menu</Button>} items={[{ label: "Open folder", onSelect: () => {} }, { label: "Delete project", onSelect: () => {}, danger: true }]} />
      <Tooltip content="Retry the failed job"><IconButton label="Retry">↻</IconButton></Tooltip>
      <Dialog open={dialog} onOpenChange={setDialog} title="Delete project" description="This removes the project and its workspace. You cannot undo this."
        footer={<><Button variant="ghost" onClick={() => setDialog(false)}>Cancel</Button><Button variant="danger" onClick={() => setDialog(false)}>Delete project</Button></>}>
        Regressed Son of a Duke, 3 chapters.
      </Dialog>
      <Drawer open={drawer} onOpenChange={setDrawer} title="Job details" description="H3 clip 4 of 7">Out of GPU memory. Ollama was holding 9 GB.</Drawer>
    </div>
  );
};

const Gallery: React.FC = () => {
  const [tab, setTab] = React.useState("engine");
  const [on, setOn] = React.useState(true);
  return (
    <div className="pf-canvas min-h-screen px-8 py-10">
      <div className="mx-auto grid max-w-5xl gap-10">
        <PageHeader title="UI v2 gallery" meta={<><Chip tone="accent">Midnight Glass</Chip><span>Every primitive and pattern in its states</span></>} actions={<Button variant="primary">Continue</Button>} />

        <Section title="Buttons">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="primary" loading>Loading</Button>
            <Button variant="secondary" disabled>Disabled</Button>
            <Button variant="secondary" size="sm">Small</Button>
            <IconButton label="Settings"><SlidersHorizontal size={16} /></IconButton>
          </div>
        </Section>

        <Section title="Chips, progress, skeleton">
          <div className="flex flex-wrap items-center gap-3">
            <Chip>Neutral</Chip><Chip tone="accent">Accent</Chip><Chip tone="ok">Ready</Chip><Chip tone="warn">Needs attention</Chip><Chip tone="bad">Failed</Chip>
          </div>
          <Progress value={62} label="Render progress" />
          <div className="flex gap-3"><Skeleton className="h-10 w-40" /><Skeleton className="h-10 w-24" /></div>
        </Section>

        <Section title="Rows and inbox">
          <GlassPanel className="grid gap-1 p-3">
            <InboxRow kind="review" selected title="OCR review, chapter 52" subtitle="3 flagged crops" actionLabel="Review" onAction={() => {}} />
            <InboxRow kind="review" title="Approve script, Dawn Gate ep. 4" subtitle="Rewritten after story check" actionLabel="Review" onAction={() => {}} />
            <InboxRow kind="blocked" title="Rights decision, Magic Emperor" subtitle="Source unknown, render held" actionLabel="Decide" onAction={() => {}} />
            <InboxRow kind="failed" title="H3 clip 4 of 7 failed" subtitle="Out of GPU memory" actionLabel="Retry" onAction={() => {}} />
            <InboxRow kind="publish" title="Upload kit, 2 videos" subtitle="Private, nothing scheduled" actionLabel="Open kit" onAction={() => {}} />
            <ListRow title="Plain selectable row" subtitle="onSelect makes the whole row a button" onSelect={() => {}} />
          </GlassPanel>
        </Section>

        <Section title="Tiles">
          <div className="grid grid-cols-4 gap-4">
            <Tile title="Regressed Son of a Duke" subtitle="OCR, 41 of 44 approved" fallbackText="RS" onOpen={() => {}} />
            <Tile title="Magic Emperor" subtitle="Story analysed" fallbackText="ME" onOpen={() => {}} />
            <Tile title="Why We Cry" subtitle="Stills video built" fallbackText="WC" onOpen={() => {}} />
            <Tile title="Moon Tales" subtitle="Series, 3 episodes" fallbackText="MT" onOpen={() => {}} />
          </div>
        </Section>

        <Section title="Jobs, engine, stepper">
          <div className="grid grid-cols-3 gap-4">
            <JobCard title="Rendering Dawn Gate" detail="Scene 9 of 14" state="running" progress={62} onCancel={() => {}} />
            <JobCard title="Voice, chapter 52" detail="Queued behind 1 job" state="queued" onCancel={() => {}} />
            <JobCard title="H3 clip 4 of 7" detail="Out of GPU memory" state="failed" onRetry={() => {}} />
          </div>
          <div className="flex flex-wrap items-center gap-4"><EngineStatus connected version="v1.0.0-beta.2" gpu="13.1 / 16 GB" /><EngineStatus connected={false} /></div>
          <Stepper steps={[
            { id: "a", label: "Source", status: "done" }, { id: "b", label: "Panels", status: "done" }, { id: "c", label: "OCR", status: "active" },
            { id: "d", label: "Story", status: "stale" }, { id: "e", label: "Script", status: "blocked" }, { id: "f", label: "Audio", status: "upcoming" },
          ]} />
        </Section>

        <Section title="Forms and tabs">
          <GlassPanel className="grid max-w-xl gap-4 p-5">
            <Field label="Project name" hint="Shown on the project tile."><Input placeholder="Moon Tales" /></Field>
            <Field label="Series name" error="Enter a name for the series."><Input defaultValue="" /></Field>
            <Field label="Genre"><Select><option>Fantasy</option><option>Slice of life</option></Select></Field>
            <Switch checked={on} onCheckedChange={setOn} label="Private by default" />
            <Tabs value={tab} onValueChange={setTab} tabs={[{ value: "engine", label: "Engine" }, { value: "models", label: "Models" }]}>
              <p className="text-sm text-fg-dim">Panel for {tab}.</p>
            </Tabs>
          </GlassPanel>
        </Section>

        <Section title="Empty and error states">
          <div className="grid grid-cols-2 gap-4">
            <GlassPanel><EmptyState title="Nothing needs you" description="Start a project or open the upload kit." action={<Button variant="primary">New project</Button>} /></GlassPanel>
            <GlassPanel><ErrorState title="This project no longer exists" description="It may have been deleted. Go back to your projects." onBack={() => {}} onRetry={() => {}} /></GlassPanel>
          </div>
        </Section>

        <Section title="Overlays">
          <Overlays />
        </Section>

        <Dock items={DOCK} activeId="home" />
      </div>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ToastProvider>
      <Gallery />
    </ToastProvider>
  </React.StrictMode>,
);
