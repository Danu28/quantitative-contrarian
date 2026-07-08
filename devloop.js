#!/usr/bin/env node

  /**
   * DEV-LOOP CLI
   */

const fs = require("fs");
const path = require("path");

const BASE_PATH = process.cwd();
const STATE_PATH = path.join(BASE_PATH, ".devloop/state.json");
const TASKS_PATH = path.join(BASE_PATH, ".devloop/tasks.json");
const CONTEXT_PATH = path.join(BASE_PATH, ".devloop/context.md");

function readJSON(filePath) {
  try {
    const data = fs.readFileSync(filePath, "utf8");
    return JSON.parse(data);
  } catch (err) {
    console.error(`❌ Error reading ${filePath}:`, err.message);
    process.exit(1);
  }
}

function writeJSON(filePath, data) {
  try {
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n");
    return true;
  } catch (err) {
    console.error(`❌ Error writing ${filePath}:`, err.message);
    process.exit(1);
  }
}

function showStatus() {
  const state = readJSON(STATE_PATH);
  const tasksData = readJSON(TASKS_PATH);
  const tasks = tasksData.tasks || [];

  console.log("\n" + "=".repeat(50));
  console.log("📊 DEV-LOOP STATUS");
  console.log("=".repeat(50) + "\n");
  
  console.log("📌 Project:", state.project.name);
  console.log("🎯 Mode:", state.execution.mode);
  console.log("⚙️  Status:", state.execution.status);

  const completed = tasks.filter((task) => task.status === "done").length;
  const total = tasks.length;
  const percent = total === 0 ? 0 : ((completed / total) * 100).toFixed(2);

  console.log("\n📈 Progress:");
  console.log(`   Completed: ${completed}/${total} (${percent}%)`);
  console.log(`   Pending: ${total - completed}`);

  const currentTask = tasks.find(
    (task) => task.id === state.execution.current_task_id,
  );

  if (currentTask) {
    console.log("\n▶️  Current Task:");
    console.log(`   #${currentTask.id} - ${currentTask.title}`);
    console.log(`   Status: ${currentTask.status}`);
    console.log(`   Priority: ${currentTask.priority}`);
  }

  console.log("\n✅ Completed Tasks:");
  const doneTasks = tasks.filter((task) => task.status === "done");
  if (doneTasks.length === 0) {
    console.log("   (none yet)");
  } else {
    doneTasks.forEach((task) => console.log(`   ✓ ${task.title}`));
  }

  console.log("\n⏳ Pending Tasks:");
  const pendingTasks = tasks.filter((task) => task.status !== "done");
  if (pendingTasks.length === 0 && total > 0) {
    console.log("   🎉 All tasks complete!");
  } else {
    pendingTasks.slice(0, 5).forEach((task) => console.log(`   • ${task.title}`));
    if (pendingTasks.length > 5) {
      console.log(`   ... and ${pendingTasks.length - 5} more`);
    }
  }

  if (state.error.has_error) {
    console.log("\n🚨 ERROR:");
    console.log(`   Task #${state.error.last_failed_task_id}`);
    console.log(`   Message: ${state.error.last_error_message}`);
    console.log("   💡 Run: devloop fix");
  }

  console.log("\n" + "=".repeat(50) + "\n");
}

function completeTask(taskId) {
  const state = readJSON(STATE_PATH);
  const tasksData = readJSON(TASKS_PATH);
  const task = tasksData.tasks.find((item) => item.id === taskId);

  if (!task) {
    console.error("❌ Task not found:", taskId);
    return;
  }

  if (task.status === "done") {
    console.log("⚠️  Task already completed:", taskId);
    return;
  }

  // Validate dependencies
  if (task.dependencies && task.dependencies.length > 0) {
    const incompleteDeps = task.dependencies.filter(depId => {
      const depTask = tasksData.tasks.find(t => t.id === depId);
      return !depTask || depTask.status !== "done";
    });
    
    if (incompleteDeps.length > 0) {
      console.error("❌ Cannot complete task. Incomplete dependencies:", incompleteDeps);
      return;
    }
  }

  task.status = "done";
  task.completed_at = new Date().toISOString();

  state.execution.last_completed_task_id = taskId;
  state.execution.current_task_id = taskId + 1;
  state.progress.completed_tasks.push(taskId);
  state.progress.pending_tasks = state.progress.pending_tasks.filter(
    (id) => id !== taskId,
  );
  state.execution.last_updated = new Date().toISOString();
  state.execution.status = "idle";

  writeJSON(TASKS_PATH, tasksData);
  writeJSON(STATE_PATH, state);

  console.log(`✅ Task ${taskId} completed: ${task.title}`);
  
  // Show next task
  const nextTask = tasksData.tasks.find(t => t.id === taskId + 1);
  if (nextTask) {
    console.log(`👉 Next: Task ${nextTask.id} - ${nextTask.title}`);
  } else {
    console.log("🎉 All tasks complete!");
  }
}

function setError(message) {
  const state = readJSON(STATE_PATH);

  state.error.has_error = true;
  state.error.last_error_message = message;
  state.error.last_failed_task_id = state.execution.current_task_id;
  state.execution.status = "blocked";
  state.execution.last_updated = new Date().toISOString();

  writeJSON(STATE_PATH, state);

  console.log("🚨 Error recorded.");
  console.log(`   Task #${state.error.last_failed_task_id}`);
  console.log("   💡 Switch to DEBUG mode and run: devloop fix");
}

function clearError() {
  const state = readJSON(STATE_PATH);

  state.error.has_error = false;
  state.error.last_error_message = null;
  state.error.last_failed_task_id = null;
  state.execution.status = "idle";
  state.execution.last_updated = new Date().toISOString();

  writeJSON(STATE_PATH, state);

  console.log("✅ Error cleared. Ready to resume.");
}

function showHelp() {
  console.log(`
📦 DEV-LOOP CLI - Project Workflow Engine

Commands:
  devloop status          Show current project progress
  devloop done <id>       Mark task as complete
  devloop error <msg>     Record an error (blocks execution)
  devloop fix             Clear error and resume
  devloop help            Show this help message

Examples:
  devloop status
  devloop done 5
  devloop error "Build failed: missing dependency"
  devloop fix

Files:
  .devloop/state.json     Execution state
  .devloop/tasks.json     Task list
  .devloop/context.md     Project context
`);
}

function showCurrentTask() {
  const state = readJSON(STATE_PATH);
  const tasksData = readJSON(TASKS_PATH);
  
  const currentTask = tasksData.tasks.find(
    (task) => task.id === state.execution.current_task_id,
  );

  if (!currentTask) {
    console.log("⚠️  No active task. All tasks may be complete.");
    return;
  }

  console.log("\n📋 Current Task:");
  console.log(`   ID: ${currentTask.id}`);
  console.log(`   Title: ${currentTask.title}`);
  console.log(`   Description: ${currentTask.description}`);
  console.log(`   Priority: ${currentTask.priority}`);
  console.log(`   Dependencies: ${currentTask.dependencies.length > 0 ? currentTask.dependencies.join(", ") : "none"}`);
  console.log("");
}

const command = process.argv[2];
const arg = process.argv.slice(3).join(" ");

switch (command) {
  case "status":
    showStatus();
    break;
  case "done":
    if (!arg) {
      console.log("❌ Usage: devloop done <taskId>");
      break;
    }
    completeTask(Number(arg));
    break;
  case "error":
    if (!arg) {
      console.log("❌ Usage: devloop error <message>");
      break;
    }
    setError(arg);
    break;
  case "fix":
    clearError();
    break;
  case "task":
    showCurrentTask();
    break;
  case "help":
  case "--help":
  case "-h":
    showHelp();
    break;
  default:
    showHelp();
    break;
}
