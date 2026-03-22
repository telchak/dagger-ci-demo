import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, Item, ItemDetail, FunctionInfo } from '../services/api.service';

@Component({
  selector: 'app-items',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './items.component.html',
})
export class ItemsComponent implements OnInit {
  items: Item[] = [];
  categories: string[] = [];
  activeFilter = 'all';
  loading = true;
  error = '';
  selectedModule: ItemDetail | null = null;
  detailLoading = false;
  activeTab = 'overview';
  selectedFunction: FunctionInfo | null = null;
  copied = false;

  private api = inject(ApiService);

  get filteredItems(): Item[] {
    if (this.activeFilter === 'all') return this.items;
    return this.items.filter(i => i.category === this.activeFilter);
  }

  get publicFunctions(): FunctionInfo[] {
    return this.selectedModule?.functions?.filter(f => !f.name.startsWith('_')) ?? [];
  }

  async ngOnInit(): Promise<void> {
    try {
      const [items, categories] = await Promise.all([
        this.api.getItems(),
        this.api.getCategories(),
      ]);
      this.items = items;
      this.categories = categories;
    } catch {
      this.error = 'Failed to load modules. Is the backend running?';
    } finally {
      this.loading = false;
    }
  }

  setFilter(category: string): void {
    this.activeFilter = category;
  }

  async selectModule(item: Item): Promise<void> {
    this.detailLoading = true;
    this.activeTab = 'overview';
    this.selectedFunction = null;
    try {
      this.selectedModule = await this.api.getItem(item.name);
    } catch {
      this.error = 'Failed to load module details.';
    } finally {
      this.detailLoading = false;
    }
  }

  closeDetail(): void {
    this.selectedModule = null;
    this.selectedFunction = null;
  }

  setTab(tab: string): void {
    this.activeTab = tab;
    this.selectedFunction = null;
  }

  selectFunction(fn: FunctionInfo): void {
    this.selectedFunction = this.selectedFunction?.name === fn.name ? null : fn;
  }

  async copyInstall(): Promise<void> {
    if (!this.selectedModule) return;
    await navigator.clipboard.writeText(this.selectedModule.install_command);
    this.copied = true;
    setTimeout(() => this.copied = false, 2000);
  }

  formatParamName(name: string): string {
    return name.replace(/_/g, '-');
  }
}
