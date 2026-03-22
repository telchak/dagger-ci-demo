import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../environments/environment';

export interface Dependency {
  name: string;
  source: string;
}

export interface FunctionParam {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default: string;
}

export interface FunctionInfo {
  name: string;
  description: string;
  is_check: boolean;
  is_async: boolean;
  return_type: string;
  params: FunctionParam[];
}

export interface Example {
  language: string;
  filename: string;
  code: string;
}

export interface Item {
  id: number;
  name: string;
  description: string;
  category: string;
  sdk: string;
  version: string;
  engine_version: string;
  dependencies: Dependency[];
  install_command: string;
  github_url: string;
  daggerverse_url: string;
}

export interface ItemDetail extends Item {
  readme: string;
  functions: FunctionInfo[];
  examples: Example[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = environment.apiUrl;
  private http = inject(HttpClient);

  async getItems(): Promise<Item[]> {
    return this.http
      .get<Item[]>(`${this.baseUrl}/api/items`)
      .toPromise() as Promise<Item[]>;
  }

  async getItem(name: string): Promise<ItemDetail> {
    return this.http
      .get<ItemDetail>(`${this.baseUrl}/api/items/${name}`)
      .toPromise() as Promise<ItemDetail>;
  }

  async getCategories(): Promise<string[]> {
    return this.http
      .get<string[]>(`${this.baseUrl}/api/categories`)
      .toPromise() as Promise<string[]>;
  }
}
